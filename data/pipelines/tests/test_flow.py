"""Test end-to-end del flow de Prefect contra SQLite en memoria.

Usa `prefect_test_harness` (motor de Prefect local, sin servidor) para
ejecutar el @flow real con sus @task reales. Supabase no esta disponible en
este entorno (proyecto pausado), asi que se monkeypatchea la conexion
(get_engine) y se fuerza schema="" en las tasks de carga, porque SQLite no
soporta `reporting.tabla` como Postgres. Verifica ademas que el paso opcional
(`export_eval_snapshot`, invocado con return_state=True) no tira abajo el
flow cuando falla.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exec_weekly_inventory_kpis import extract, flow as flow_module
from exec_weekly_inventory_kpis import load

WEEK_START = datetime(2026, 8, 24, tzinfo=timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE telemetry_events ("
                "event_id TEXT PRIMARY KEY, timestamp TIMESTAMP, session_id TEXT, user_id TEXT, "
                "event_type TEXT, schema_version TEXT, request_id TEXT, properties TEXT)"
            )
        )
        connection.execute(
            text("CREATE TABLE sku (id INTEGER, name TEXT, sku TEXT, client_name TEXT, category TEXT, warehouse TEXT)")
        )
        connection.execute(text("INSERT INTO sku VALUES (1, 'Shoe', 'SKU-1', 'Acme', 'fashion', 'LA')"))
        properties = '{"warehouse": "LA", "client_id": "Acme", "product_id": "SKU-1", "product_category": "fashion", "quantity": 9}'
        connection.execute(
            text("INSERT INTO telemetry_events VALUES ('e1', :ts, 's', 'u', 'outbound_order_created', '1.0', 'r', :props)"),
            {"ts": WEEK_START + timedelta(hours=1), "props": properties},
        )

    monkeypatch.setattr(flow_module, "get_engine", lambda: engine)
    return engine


@pytest.fixture
def force_empty_schema(monkeypatch, tmp_path):
    """Reescribe las tasks/funciones de carga para que siempre usen schema="" (SQLite)
    y redirige el snapshot opcional a un directorio temporal (no data/eval/ real).

    En produccion (Postgres) el flow usa el default "reporting" de load.py sin
    tocar nada de esto; este fixture solo existe para poder correr el flow
    real contra SQLite sin tener Supabase disponible.
    """
    original_extract_task = flow_module.extract_inventory_events
    original_load_weekly_kpis_task = flow_module.load_weekly_kpis
    original_finalize_run_task = flow_module.finalize_run
    original_export_eval_snapshot_task = flow_module.export_eval_snapshot
    original_ensure_schema = load.ensure_schema
    original_open_run = load.open_run

    def extract_inventory_events_sqlite(engine, week_start, week_end):
        # SQLite no tiene tipo JSON nativo: properties vuelve como TEXT, no
        # como dict (en Postgres/JSONB, psycopg2 ya lo deserializa). Solo
        # afecta a este test; extract.py en si no cambia.
        events_df = extract.extract_inventory_events(engine, week_start, week_end)
        if not events_df.empty and isinstance(events_df.iloc[0]["properties"], str):
            events_df = events_df.copy()
            events_df["properties"] = events_df["properties"].apply(json.loads)
        return events_df

    def load_weekly_kpis_sqlite(engine, kpis_df, sku_df, run_id, schema=""):
        return load.load_weekly_kpis(engine, kpis_df, sku_df, run_id, schema="")

    def close_run_sqlite(engine, run_id, *, status, counters, schema=""):
        return load.close_run(engine, run_id, status=status, counters=counters, schema="")

    def export_eval_snapshot_to_tmp(kpis_df, run_id, iso_week, qc, eval_dir=tmp_path):
        return flow_module.notify.export_eval_snapshot(kpis_df, run_id, iso_week, qc, eval_dir=tmp_path)

    flow_module.extract_inventory_events = flow_module.task(
        name="extract_inventory_events", retries=3, retry_delay_seconds=[10, 30, 90]
    )(extract_inventory_events_sqlite)
    flow_module.load_weekly_kpis = flow_module.task(
        name="load_weekly_kpis", retries=2, retry_delay_seconds=15
    )(load_weekly_kpis_sqlite)
    flow_module.finalize_run = flow_module.task(name="finalize_run", retries=2, retry_delay_seconds=5)(close_run_sqlite)
    flow_module.export_eval_snapshot = flow_module.task(name="export_eval_snapshot", retries=0)(export_eval_snapshot_to_tmp)
    load.ensure_schema = lambda engine, schema="": original_ensure_schema(engine, schema="")
    load.open_run = lambda engine, **kwargs: original_open_run(
        engine, schema="", **{key: value for key, value in kwargs.items() if key != "schema"}
    )

    try:
        yield
    finally:
        flow_module.extract_inventory_events = original_extract_task
        flow_module.load_weekly_kpis = original_load_weekly_kpis_task
        flow_module.finalize_run = original_finalize_run_task
        flow_module.export_eval_snapshot = original_export_eval_snapshot_task
        load.ensure_schema = original_ensure_schema
        load.open_run = original_open_run


def test_flow_runs_end_to_end_and_persists_kpis(sqlite_engine, force_empty_schema):
    result = flow_module.exec_weekly_inventory_kpis_flow(iso_week="2026-W35", trigger="manual")

    assert result["iso_week"] == "2026-W35"
    assert result["rows_inserted"] == 1

    with sqlite_engine.connect() as connection:
        row = connection.execute(text("SELECT fulfillment_rate FROM exec_weekly_inventory_kpis")).one()
    assert row[0] == pytest.approx(1.0)  # solo outbound, sin stock_threshold_triggered -> 100% cumplimiento

    with sqlite_engine.connect() as connection:
        status = connection.execute(text("SELECT status FROM pipeline_runs WHERE run_id = :run_id"), {"run_id": result["run_id"]}).scalar()
    assert status == "completed"


def test_flow_is_idempotent_on_rerun_over_the_same_week(sqlite_engine, force_empty_schema):
    """Fase 3: correr el flow dos veces sobre el mismo rango debe dejar una
    unica fila con los mismos KPIs (solo cambian run_id/computed_at)."""
    first = flow_module.exec_weekly_inventory_kpis_flow(iso_week="2026-W35", trigger="manual")
    second = flow_module.exec_weekly_inventory_kpis_flow(iso_week="2026-W35", trigger="manual")

    assert first["rows_inserted"] == 1
    assert second["rows_inserted"] == 0
    assert second["rows_updated"] == 1
    assert first["run_id"] != second["run_id"]

    with sqlite_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT fulfillment_rate, outbound_qty, pipeline_run_id FROM exec_weekly_inventory_kpis")
        ).fetchall()
    assert len(rows) == 1  # nunca se duplica la fila de la semana
    assert rows[0][0] == pytest.approx(1.0)
    assert rows[0][1] == 9
    assert rows[0][2] == second["run_id"]  # la promocion mas reciente gano


def test_optional_export_snapshot_failure_does_not_break_the_flow(sqlite_engine, force_empty_schema, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("disco lleno (simulado)")

    monkeypatch.setattr(flow_module, "export_eval_snapshot", flow_module.task(name="export_eval_snapshot", retries=0)(_boom))

    result = flow_module.exec_weekly_inventory_kpis_flow(iso_week="2026-W35", trigger="manual")

    # La carga (extract -> transform -> load) se completo igual; el paso
    # opcional fallo pero no propago la excepcion gracias a return_state=True.
    assert result["rows_inserted"] == 1
    with sqlite_engine.connect() as connection:
        status = connection.execute(text("SELECT status FROM pipeline_runs WHERE run_id = :run_id"), {"run_id": result["run_id"]}).scalar()
    assert status == "completed"


def test_run_id_provided_by_caller_is_reused_not_recreated(sqlite_engine, force_empty_schema):
    """Fase 5: POST /run abre la fila de pipeline_runs antes de lanzar el flow
    (para devolver run_id en la respuesta 202) y se la pasa al flow."""
    load.ensure_schema(sqlite_engine, schema="")
    extract_start, week_start, week_end, resolved_iso_week = flow_module.resolve_extraction_window("2026-W35")
    pre_created_run_id = load.open_run(
        sqlite_engine,
        trigger="manual",
        triggered_by="42",
        window_from=extract_start,
        window_to=week_end,
        iso_week=resolved_iso_week,
        schema="",
    )

    result = flow_module.exec_weekly_inventory_kpis_flow(iso_week="2026-W35", trigger="manual", run_id=pre_created_run_id)

    assert result["run_id"] == pre_created_run_id
    with sqlite_engine.connect() as connection:
        run_count = connection.execute(text("SELECT COUNT(*) FROM pipeline_runs")).scalar()
    assert run_count == 1  # no se creo una segunda fila


def test_weekly_kpis_cache_key_is_stable_for_identical_inputs_and_changes_with_data():
    week_start = WEEK_START
    week_end = week_start + timedelta(days=7)
    events_df = pd.DataFrame([{"event_id": "e1"}, {"event_id": "e2"}])
    sku_df = pd.DataFrame([{"id": 1, "name": "Shoe", "client_name": "Acme", "category": "fashion", "warehouse": "LA"}])

    key_a = flow_module._weekly_kpis_cache_key(None, {"events_df": events_df, "sku_df": sku_df, "week_start": week_start, "week_end": week_end})
    key_b = flow_module._weekly_kpis_cache_key(None, {"events_df": events_df.copy(), "sku_df": sku_df.copy(), "week_start": week_start, "week_end": week_end})
    assert key_a == key_b  # mismos inputs -> misma clave (cacheable)

    changed_events_df = pd.DataFrame([{"event_id": "e1"}, {"event_id": "e3"}])
    key_c = flow_module._weekly_kpis_cache_key(None, {"events_df": changed_events_df, "sku_df": sku_df, "week_start": week_start, "week_end": week_end})
    assert key_c != key_a  # llego un evento distinto -> no debe servirse el cache viejo

    changed_sku_df = pd.DataFrame([{"id": 1, "name": "Shoe", "client_name": "Acme", "category": "electronics", "warehouse": "LA"}])
    key_d = flow_module._weekly_kpis_cache_key(None, {"events_df": events_df, "sku_df": changed_sku_df, "week_start": week_start, "week_end": week_end})
    assert key_d != key_a  # SKU es mutable: un cambio de categoria tambien debe invalidar el cache
