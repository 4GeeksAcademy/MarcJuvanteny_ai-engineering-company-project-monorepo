"""Tests de carga (load.py) y extraccion (extract.py) contra SQLite en memoria.

No hay Supabase disponible en este entorno (proyecto pausado, ver
Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md, pendiente #5), asi
que estos tests validan la logica SQL real (UPSERT, dedupe, idempotencia)
contra SQLite con schema="" (SQLite no soporta esquemas con nombre como
Postgres). El DDL de produccion es exec_weekly_inventory_kpis/schema.sql.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exec_weekly_inventory_kpis import extract, load
from exec_weekly_inventory_kpis.config import INVENTORY_EVENT_TYPES

WEEK_START = datetime(2026, 8, 24, tzinfo=timezone.utc)
WEEK_END = WEEK_START + timedelta(days=7)


@pytest.fixture
def engine():
    return create_engine("sqlite:///:memory:")


def _seed_telemetry_events(engine, rows):
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE telemetry_events ("
                "event_id TEXT PRIMARY KEY, timestamp TIMESTAMP, session_id TEXT, user_id TEXT, "
                "event_type TEXT, schema_version TEXT, request_id TEXT, properties TEXT)"
            )
        )
        for row in rows:
            connection.execute(text("INSERT INTO telemetry_events VALUES (:event_id, :timestamp, :session_id, :user_id, :event_type, :schema_version, :request_id, :properties)"), row)


def test_extract_inventory_events_filters_by_window_and_event_type(engine):
    in_window_inventory = {
        "event_id": "e1", "timestamp": WEEK_START + timedelta(hours=1), "session_id": "s", "user_id": "u",
        "event_type": "inbound_order_created", "schema_version": "1.0", "request_id": "r", "properties": "{}",
    }
    in_window_other = {**in_window_inventory, "event_id": "e2", "event_type": "auth_login_attempted"}
    out_of_window = {**in_window_inventory, "event_id": "e3", "timestamp": WEEK_END + timedelta(hours=1)}
    _seed_telemetry_events(engine, [in_window_inventory, in_window_other, out_of_window])

    result = extract.extract_inventory_events(engine, WEEK_START, WEEK_END)

    assert list(result["event_id"]) == ["e1"]
    assert set(INVENTORY_EVENT_TYPES) >= set(result["event_type"])


def test_ensure_schema_is_idempotent(engine):
    load.ensure_schema(engine, schema="")
    load.ensure_schema(engine, schema="")  # segunda llamada no debe fallar


def test_load_weekly_kpis_upsert_is_idempotent_on_rerun(engine):
    load.ensure_schema(engine, schema="")
    sku_df = pd.DataFrame([{"id": 1, "name": "Shoe", "sku": "SKU-1", "client_name": "Acme", "category": "fashion", "warehouse": "LA"}])
    kpis_df = pd.DataFrame(
        [
            {
                "iso_week": "2026-W35", "week_start": WEEK_START, "week_end": WEEK_END, "warehouse": "LA",
                "country": "USA", "client_id": "Acme", "inbound_orders": 1, "outbound_orders": 1,
                "inbound_qty": 10, "outbound_qty": 9, "stock_threshold_events": 0, "discrepancy_events": 0,
                "governance_flags": 0, "fulfillment_rate": 0.9, "discrepancy_frequency": 0.0,
                "receipt_to_dispatch_cycle_time_h": 12.0, "events_considered": 2,
            }
        ]
    )
    run_id_1 = str(uuid.uuid4())

    inserted_1, updated_1, _ = load.load_weekly_kpis(engine, kpis_df, sku_df, run_id_1, schema="")
    assert (inserted_1, updated_1) == (1, 0)

    # Re-run de la misma semana: debe sobrescribir la fila existente, no duplicarla.
    run_id_2 = str(uuid.uuid4())
    kpis_df_v2 = kpis_df.copy()
    kpis_df_v2.loc[0, "outbound_qty"] = 20
    inserted_2, updated_2, _ = load.load_weekly_kpis(engine, kpis_df_v2, sku_df, run_id_2, schema="")
    assert (inserted_2, updated_2) == (0, 1)

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT outbound_qty, pipeline_run_id FROM exec_weekly_inventory_kpis")).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 20
    assert rows[0][1] == run_id_2


def test_reconcile_dim_sku_deactivates_removed_skus(engine):
    load.ensure_schema(engine, schema="")
    first_snapshot = pd.DataFrame([{"id": 1, "name": "Shoe", "sku": "SKU-1", "client_name": "Acme", "category": "fashion", "warehouse": "LA"}])
    load.reconcile_dim_sku(engine, first_snapshot, schema="")

    second_snapshot = pd.DataFrame(columns=first_snapshot.columns)  # SKU-1 ya no existe
    deactivated = load.reconcile_dim_sku(engine, second_snapshot, schema="")

    assert deactivated == 1
    with engine.connect() as connection:
        is_current = connection.execute(text("SELECT is_current FROM dim_sku WHERE sku_id = 1")).scalar()
    assert is_current == 0


def test_open_run_then_close_run_updates_status_and_counters(engine):
    load.ensure_schema(engine, schema="")
    run_id = load.open_run(
        engine,
        trigger="manual",
        triggered_by="pytest",
        window_from=WEEK_START,
        window_to=WEEK_END,
        iso_week="2026-W35",
        schema="",
    )
    load.close_run(engine, run_id, status="completed", counters={"rows_read": 5, "rows_rejected": 0}, schema="")

    with engine.connect() as connection:
        status, rows_read = connection.execute(
            text("SELECT status, rows_read FROM pipeline_runs WHERE run_id = :run_id"), {"run_id": run_id}
        ).one()
    assert status == "completed"
    assert rows_read == 5
