"""Carga (Fase 2.5 / 3.1 / 3.2 del diseno): I/O de escritura + bookkeeping.

Staging -> promocion transaccional vía UPSERT por clave natural
`(iso_week, warehouse, client_id)`, reconciliacion de `dim_sku` por `sku_id`,
y log de ejecucion en `pipeline_runs`. Si el proceso muere antes del COMMIT de
`promote_kpis`, Postgres revierte y la tabla final queda intacta (Fase 3.1).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import Engine, delete, select, text

from .config import DIM_SKU_TABLE, FACT_TABLE, PIPELINE_NAME, PIPELINE_VERSION, REPORTING_SCHEMA, RUNS_TABLE, STAGING_TABLE
from .schema import build_metadata


def ensure_schema(engine: Engine, schema: str = REPORTING_SCHEMA) -> None:
    """Crea el esquema (si aplica) y las tablas si no existen. Idempotente."""
    if schema and engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    build_metadata(schema).create_all(engine, checkfirst=True)


def stage_kpis(engine: Engine, kpis_df: pd.DataFrame, run_id: str, schema: str = REPORTING_SCHEMA) -> None:
    """Vacia y rellena la tabla de staging con el DataFrame completo de la corrida."""
    metadata = build_metadata(schema)
    staging_table = metadata.tables[f"{schema}.{STAGING_TABLE}" if schema else STAGING_TABLE]

    staged = kpis_df.copy()
    staged["pipeline_run_id"] = run_id
    staged["computed_at"] = datetime.now(timezone.utc)

    with engine.begin() as connection:
        connection.execute(delete(staging_table))
        if not staged.empty:
            connection.execute(staging_table.insert(), staged.to_dict(orient="records"))


def _upsert_insert(engine: Engine, table):
    """`INSERT ... ON CONFLICT DO UPDATE` builder, portable Postgres/SQLite.

    SQLite no acepta el upsert-clause tras un `INSERT ... SELECT` (solo tras
    `INSERT ... VALUES`), asi que `promote_kpis` construye el INSERT con los
    valores ya traidos a Python en vez de un `INSERT INTO ... SELECT` crudo;
    en Postgres el resultado es el mismo UPSERT atomico de una sola sentencia.
    """
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as postgresql_insert

        return postgresql_insert(table)
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    return sqlite_insert(table)


def promote_kpis(engine: Engine, schema: str = REPORTING_SCHEMA) -> tuple[int, int]:
    """Promociona staging -> tabla final en una unica transaccion (UPSERT por clave natural).

    Devuelve `(rows_inserted, rows_updated)`.
    """
    metadata = build_metadata(schema)
    fact_name = f"{schema}.{FACT_TABLE}" if schema else FACT_TABLE
    staging_name = f"{schema}.{STAGING_TABLE}" if schema else STAGING_TABLE
    fact_table = metadata.tables[fact_name]
    staging_table = metadata.tables[staging_name]
    update_columns = [c.name for c in fact_table.columns if c.name not in ("iso_week", "warehouse", "client_id")]

    with engine.begin() as connection:
        existing_keys = {
            tuple(row)
            for row in connection.execute(select(fact_table.c.iso_week, fact_table.c.warehouse, fact_table.c.client_id))
        }
        staged_rows = [dict(row._mapping) for row in connection.execute(select(staging_table))]
        staged_keys = {(row["iso_week"], row["warehouse"], row["client_id"]) for row in staged_rows}
        rows_updated = len(existing_keys & staged_keys)
        rows_inserted = len(staged_keys - existing_keys)

        if staged_rows:
            insert_stmt = _upsert_insert(engine, fact_table).values(staged_rows)
            insert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["iso_week", "warehouse", "client_id"],
                set_={column: getattr(insert_stmt.excluded, column) for column in update_columns},
            )
            connection.execute(insert_stmt)

    return rows_inserted, rows_updated


def reconcile_dim_sku(engine: Engine, sku_df: pd.DataFrame, schema: str = REPORTING_SCHEMA) -> int:
    """UPSERT del snapshot de SKU en `reporting.dim_sku` + marca `is_current=false` para los ausentes.

    Devuelve el numero de filas desactivadas (SKUs borrados/renombrados desde la ultima corrida).
    """
    metadata = build_metadata(schema)
    dim_name = f"{schema}.{DIM_SKU_TABLE}" if schema else DIM_SKU_TABLE
    dim_table = metadata.tables[dim_name]
    seen_at = datetime.now(timezone.utc)

    with engine.begin() as connection:
        for _, row in sku_df.iterrows():
            connection.execute(
                text(
                    f"INSERT INTO {dim_name} (sku_id, sku, name, client_name, category, warehouse, is_current, seen_at) "
                    "VALUES (:sku_id, :sku, :name, :client_name, :category, :warehouse, 1, :seen_at) "
                    "ON CONFLICT (sku_id) DO UPDATE SET "
                    "sku = excluded.sku, name = excluded.name, client_name = excluded.client_name, "
                    "category = excluded.category, warehouse = excluded.warehouse, "
                    "is_current = 1, seen_at = excluded.seen_at"
                ),
                {
                    "sku_id": int(row["id"]),
                    "sku": row["sku"],
                    "name": row["name"],
                    "client_name": row["client_name"],
                    "category": row["category"],
                    "warehouse": row["warehouse"],
                    "seen_at": seen_at,
                },
            )

        current_ids = tuple(int(v) for v in sku_df["id"]) if not sku_df.empty else (-1,)
        placeholders = ", ".join(f":id{i}" for i in range(len(current_ids)))
        result = connection.execute(
            text(
                f"UPDATE {dim_name} SET is_current = 0 "
                f"WHERE sku_id NOT IN ({placeholders}) AND is_current = 1"
            ),
            {f"id{i}": value for i, value in enumerate(current_ids)},
        )
        return result.rowcount or 0


def open_run(
    engine: Engine,
    *,
    trigger: str,
    triggered_by: str,
    window_from: datetime,
    window_to: datetime,
    iso_week: str,
    schema: str = REPORTING_SCHEMA,
) -> str:
    """Inserta la fila `running` de `pipeline_runs`. Devuelve el `run_id` (UUID str)."""
    metadata = build_metadata(schema)
    runs_name = f"{schema}.{RUNS_TABLE}" if schema else RUNS_TABLE
    runs_table = metadata.tables[runs_name]
    run_id = str(uuid.uuid4())

    with engine.begin() as connection:
        connection.execute(
            runs_table.insert(),
            {
                "run_id": run_id,
                "pipeline_name": PIPELINE_NAME,
                "pipeline_version": PIPELINE_VERSION,
                "trigger": trigger,
                "triggered_by": triggered_by,
                "window_from": window_from,
                "window_to": window_to,
                "iso_week": iso_week,
                "started_at": datetime.now(timezone.utc),
                "status": "running",
            },
        )
    return run_id


def close_run(
    engine: Engine,
    run_id: str,
    *,
    status: str,
    counters: dict[str, Any],
    schema: str = REPORTING_SCHEMA,
) -> None:
    """Cierra la fila de `pipeline_runs` con status terminal (`completed`/`failed`) y contadores."""
    runs_name = f"{schema}.{RUNS_TABLE}" if schema else RUNS_TABLE
    payload = {**counters, "run_id": run_id, "status": status, "finished_at": datetime.now(timezone.utc)}
    if "error_sample" in payload and payload["error_sample"] is not None:
        payload["error_sample"] = json.dumps(payload["error_sample"])
    set_columns = [key for key in payload if key != "run_id"]
    set_clause = ", ".join(f"{col} = :{col}" for col in set_columns)

    with engine.begin() as connection:
        connection.execute(text(f"UPDATE {runs_name} SET {set_clause} WHERE run_id = :run_id"), payload)


def load_weekly_kpis(
    engine: Engine,
    kpis_df: pd.DataFrame,
    sku_df: pd.DataFrame,
    run_id: str,
    schema: str = REPORTING_SCHEMA,
) -> tuple[int, int, int]:
    """Compone stage + promote + reconcile. Devuelve `(rows_inserted, rows_updated, sku_rows_deactivated)`."""
    stage_kpis(engine, kpis_df, run_id, schema)
    rows_inserted, rows_updated = promote_kpis(engine, schema)
    sku_rows_deactivated = reconcile_dim_sku(engine, sku_df, schema)
    return rows_inserted, rows_updated, sku_rows_deactivated
