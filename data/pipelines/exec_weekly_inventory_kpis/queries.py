"""Consultas de solo lectura sobre `reporting.*` (Fase 5.2 del diseno).

Sin dependencia de Prefect: `services/reporting/` importa estas funciones
directamente, no dispara ETL ni conoce `data/pipelines/` mas alla de esto.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import Engine, text

from .config import FACT_TABLE, PIPELINE_NAME, REPORTING_SCHEMA, RUNS_TABLE


def read_latest_run(engine: Engine, pipeline_name: str = PIPELINE_NAME, schema: str = REPORTING_SCHEMA) -> dict | None:
    """Ultima corrida del pipeline (por `started_at`), o None si no hay ninguna."""
    runs_name = f"{schema}.{RUNS_TABLE}" if schema else RUNS_TABLE
    query = text(
        f"SELECT * FROM {runs_name} WHERE pipeline_name = :pipeline_name "
        "ORDER BY started_at DESC LIMIT 1"
    )
    with engine.connect() as connection:
        row = connection.execute(query, {"pipeline_name": pipeline_name}).mappings().first()
    return dict(row) if row else None


def query_weekly_kpis(
    engine: Engine,
    from_week: str,
    to_week: str,
    warehouse: str | None = None,
    country: str | None = None,
    client_id: str | None = None,
    schema: str = REPORTING_SCHEMA,
) -> pd.DataFrame:
    """Filas materializadas de `reporting.exec_weekly_inventory_kpis` en `[from_week, to_week]`.

    Solo lectura: nunca recalcula ni toca `telemetry_events`.
    """
    fact_name = f"{schema}.{FACT_TABLE}" if schema else FACT_TABLE
    clauses = ["iso_week >= :from_week", "iso_week <= :to_week"]
    params: dict[str, str] = {"from_week": from_week, "to_week": to_week}

    if warehouse is not None:
        clauses.append("warehouse = :warehouse")
        params["warehouse"] = warehouse
    if country is not None:
        clauses.append("country = :country")
        params["country"] = country
    if client_id is not None:
        clauses.append("client_id = :client_id")
        params["client_id"] = client_id

    query = text(f"SELECT * FROM {fact_name} WHERE {' AND '.join(clauses)} ORDER BY iso_week, warehouse, client_id")
    with engine.connect() as connection:
        return pd.read_sql(query, connection, params=params)
