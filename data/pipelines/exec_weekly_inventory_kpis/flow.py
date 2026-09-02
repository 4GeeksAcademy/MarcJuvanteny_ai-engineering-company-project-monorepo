"""Flows + tasks de Prefect (Fase 4 del diseno).

Orquesta extract -> transform -> load para `reporting.exec_weekly_inventory_kpis`.
La logica de negocio vive en extract.py/transform.py/load.py como funciones
planas; este modulo solo las envuelve en @task y las conecta en un @flow, para
que ese codigo se pueda probar (y reutilizar desde `services/reporting/` via
queries.py) sin depender de Prefect.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from prefect import flow, get_run_logger, task

from . import extract, load, notify, transform
from .blocks import get_engine, get_pipeline_config
from .config import PIPELINE_NAME, PIPELINE_VERSION

# 3 reintentos con backoff exponencial [10, 30, 90]s (~2 min en total): los
# fallos de extraccion contra Supabase suelen ser transitorios (drop de
# conexion, pool agotado), no errores logicos. El backoff creciente da tiempo
# a que el pool/la red se recuperen sin martillear una BD que ya esta
# degradada (Fase 4.1 del diseno).
_EXTRACT_RETRY_KWARGS = {"retries": 3, "retry_delay_seconds": [10, 30, 90]}

extract_inventory_events = task(name="extract_inventory_events", **_EXTRACT_RETRY_KWARGS)(
    extract.extract_inventory_events
)
extract_sku_snapshot = task(name="extract_sku_snapshot", **_EXTRACT_RETRY_KWARGS)(extract.extract_sku_snapshot)


def _weekly_kpis_cache_key(context: Any, parameters: dict[str, Any]) -> str:
    """Clave de cache de `build_weekly_kpis`: version del pipeline + ventana +
    huella del contenido de `events_df`/`sku_df`.

    `build_weekly_kpis` es pura (transform.py): mismos inputs -> mismo output
    siempre, asi que cachear por contenido (no solo por semana) es seguro.
    `telemetry_events` es insert-only (Fase 2.4 del diseno), asi que el
    conjunto de `event_id` presentes en la ventana identifica su contenido sin
    tener que serializar `properties`. `SKU` si es mutable, asi que ahi se
    hashean los valores, no solo los ids.
    """
    events_df = parameters["events_df"]
    sku_df = parameters["sku_df"]
    week_start = parameters["week_start"]
    week_end = parameters["week_end"]

    event_ids = ",".join(sorted(events_df["event_id"])) if not events_df.empty else ""
    sku_fingerprint = (
        ",".join(
            f"{row.id}:{row.name}:{row.client_name}:{row.category}:{row.warehouse}"
            for row in sku_df.itertuples()
        )
        if not sku_df.empty
        else ""
    )
    raw_key = f"{PIPELINE_VERSION}|{week_start.isoformat()}|{week_end.isoformat()}|{event_ids}|{sku_fingerprint}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# Cachea el resultado 1 hora: dentro de ese margen, un re-run manual (o un
# retry de load_weekly_kpis que arrastra al flow entero, ver el except mas
# abajo) reutiliza el calculo en vez de repetir el join + emparejamiento
# inbound/outbound. Pasada 1 hora se asume que pudo llegar telemetria nueva
# dentro de la ventana de gracia y se recalcula. 0 retries porque un fallo
# aqui es un bug de la transformacion, no un problema transitorio de I/O.
build_weekly_kpis = task(
    name="build_weekly_kpis",
    retries=0,
    cache_key_fn=_weekly_kpis_cache_key,
    cache_expiration=timedelta(hours=1),
)(transform.build_weekly_kpis)

# 2 reintentos: la carga es idempotente (staging + UPSERT transaccional por
# clave natural), asi que repetirla tras un fallo es seguro y nunca duplica
# datos. Menos que extract (3) porque, si llegamos hasta aqui, ya sabemos que
# la BD respondia hace un momento (extract tuvo exito); un fallo aca es mas
# probable que sea un problema real (constraint, disco lleno) que uno
# transitorio, y no queremos enmascarar un bug reintentando de mas.
load_weekly_kpis = task(name="load_weekly_kpis", retries=2, retry_delay_seconds=15)(load.load_weekly_kpis)

# 2 reintentos, 5s: es un UPDATE de una sola fila (pipeline_runs), barato de
# reintentar; pero debe llegar a escribirse si o si, porque es la unica
# fuente de verdad de "como termino esta corrida" (Fase 3.2 del diseno) y
# GET /reporting/exec-weekly/status depende de que quede en un estado
# terminal (completed/failed), nunca colgado en running.
finalize_run = task(name="finalize_run", retries=2, retry_delay_seconds=5)(load.close_run)

# Paso opcional / no critico: 0 retries (si falla, ver mas abajo que se
# invoca con return_state=True) para que un fallo no interrumpa
# extract -> transform -> load, que para este punto ya completo y comiteo.
export_eval_snapshot = task(name="export_eval_snapshot", retries=0)(notify.export_eval_snapshot)


def resolve_week_window(iso_week: str | None) -> tuple[datetime, datetime, str]:
    """`iso_week` ("2026-W35") -> `(week_start, week_end, iso_week)` en UTC.

    Sin `iso_week`, resuelve la ultima semana ISO ya cerrada (Fase 2.2: el
    pipeline no necesita tiempo real).
    """
    if iso_week is None:
        today = datetime.now(timezone.utc).date()
        iso_today = today.isocalendar()
        this_monday = date.fromisocalendar(iso_today.year, iso_today.week, 1)
        target_monday = this_monday - timedelta(days=7)
    else:
        year_str, week_str = iso_week.split("-W")
        target_monday = date.fromisocalendar(int(year_str), int(week_str), 1)

    week_start = datetime.combine(target_monday, time.min, tzinfo=timezone.utc)
    week_end = week_start + timedelta(days=7)
    iso_cal = target_monday.isocalendar()
    resolved_iso_week = f"{iso_cal.year}-W{iso_cal.week:02d}"
    return week_start, week_end, resolved_iso_week


def resolve_extraction_window(iso_week: str | None) -> tuple[datetime, datetime, datetime, str]:
    """`(extract_start, week_start, week_end, iso_week)`, incluyendo la ventana de gracia.

    Compartida por el flow y por `POST /reporting/exec-weekly/run` (Fase 5):
    el endpoint necesita la misma ventana para abrir la fila de
    `pipeline_runs` *antes* de lanzar el flow, sin duplicar la logica de
    grace-window aqui y alla.
    """
    config = get_pipeline_config()
    week_start, week_end, resolved_iso_week = resolve_week_window(iso_week)
    extract_start = week_start - timedelta(days=config["grace_window_days"])
    return extract_start, week_start, week_end, resolved_iso_week


@flow(name="exec_weekly_inventory_kpis_flow")
def exec_weekly_inventory_kpis_flow(
    iso_week: str | None = None,
    trigger: str = "scheduled",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Consolida `reporting.exec_weekly_inventory_kpis` para una semana ISO.

    `trigger` documenta el origen de la corrida en `pipeline_runs`
    (`scheduled` | `manual` | `backfill`); no cambia el comportamiento del ETL.
    `run_id`: si ya existe una fila `running` en `pipeline_runs` (caso de
    `POST /reporting/exec-weekly/run`, que la crea de forma sincrona para
    devolver el `run_id` en la respuesta 202 antes de lanzar el flow en
    background), se reutiliza en vez de abrir una nueva.
    """
    logger = get_run_logger()
    engine = get_engine()
    load.ensure_schema(engine)

    extract_start, week_start, week_end, resolved_iso_week = resolve_extraction_window(iso_week)

    if run_id is None:
        run_id = load.open_run(
            engine,
            trigger=trigger,
            triggered_by="prefect" if trigger == "scheduled" else trigger,
            window_from=extract_start,
            window_to=week_end,
            iso_week=resolved_iso_week,
        )

    try:
        events_df = extract_inventory_events(engine, extract_start, week_end)
        sku_df = extract_sku_snapshot(engine)
        kpis_df, qc = build_weekly_kpis(events_df, sku_df, extract_start, week_end)
        rows_inserted, rows_updated, sku_rows_deactivated = load_weekly_kpis(engine, kpis_df, sku_df, run_id)
    except Exception as exc:
        finalize_run(engine, run_id, status="failed", counters={"error_message": str(exc)})
        raise

    finalize_run(
        engine,
        run_id,
        status="completed",
        counters={
            "sku_snapshot_rows": len(sku_df),
            "sku_rows_deactivated": sku_rows_deactivated,
            "rows_read": qc["rows_read"],
            "rows_rejected": qc["rows_rejected"],
            "rows_unmatched_sku": qc["rows_unmatched_sku"],
            "rows_transformed": qc["rows_transformed"],
            "rows_upserted_insert": rows_inserted,
            "rows_upserted_update": rows_updated,
            "error_count": qc["rows_rejected"],
            "error_sample": qc["error_sample"],
        },
    )

    # Paso opcional: si falla, no debe tirar abajo una corrida que ya
    # completo la carga. return_state=True evita que Prefect propague la
    # excepcion; solo se registra un warning.
    snapshot_state = export_eval_snapshot(kpis_df, run_id, resolved_iso_week, qc, return_state=True)
    if snapshot_state.is_failed():
        logger.warning(
            "export_eval_snapshot fallo para %s (run_id=%s); reporting.%s ya quedo actualizado.",
            resolved_iso_week,
            run_id,
            PIPELINE_NAME,
        )

    return {
        "run_id": run_id,
        "iso_week": resolved_iso_week,
        "rows_inserted": rows_inserted,
        "rows_updated": rows_updated,
    }


def _iter_iso_weeks(from_week: str, to_week: str):
    start_monday = date.fromisocalendar(*_split_iso_week(from_week), 1)
    end_monday = date.fromisocalendar(*_split_iso_week(to_week), 1)
    current = start_monday
    while current <= end_monday:
        iso_cal = current.isocalendar()
        yield f"{iso_cal.year}-W{iso_cal.week:02d}"
        current += timedelta(days=7)


def _split_iso_week(iso_week: str) -> tuple[int, int]:
    year_str, week_str = iso_week.split("-W")
    return int(year_str), int(week_str)


@flow(name="exec_weekly_inventory_kpis_backfill_flow")
def exec_weekly_inventory_kpis_backfill_flow(from_week: str, to_week: str) -> list[dict[str, Any]]:
    """Recorre `[from_week, to_week]` llamando al flow principal por cada semana ISO."""
    return [exec_weekly_inventory_kpis_flow(iso_week=week, trigger="backfill") for week in _iter_iso_weeks(from_week, to_week)]
