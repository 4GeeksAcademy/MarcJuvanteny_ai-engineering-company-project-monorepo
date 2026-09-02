"""Metadata SQLAlchemy Core de las tablas `reporting.*` (Fase 2.5 / 3.2 del diseno).

Fuente de verdad ejecutable para `ensure_schema()` (create_all, portable entre
Postgres y SQLite para tests). `schema.sql` es el DDL Postgres equivalente,
pensado para desplegar con `psql -f schema.sql` o una migracion.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, String, Table

from .config import DIM_SKU_TABLE, FACT_TABLE, REPORTING_SCHEMA, RUNS_TABLE, STAGING_TABLE


def build_metadata(schema: str = REPORTING_SCHEMA) -> MetaData:
    metadata = MetaData(schema=schema or None)

    # Columnas no-clave, compartidas por la tabla final y el staging (el
    # staging las declara sin primary key: se trunca/rellena cada corrida).
    def _value_columns() -> list[Column]:
        return [
            Column("week_start", DateTime(timezone=True), nullable=False),
            Column("week_end", DateTime(timezone=True), nullable=False),
            Column("country", String(16)),
            Column("inbound_orders", Integer, nullable=False, default=0),
            Column("outbound_orders", Integer, nullable=False, default=0),
            Column("inbound_qty", Numeric, nullable=False, default=0),
            Column("outbound_qty", Numeric, nullable=False, default=0),
            Column("stock_threshold_events", Integer, nullable=False, default=0),
            Column("discrepancy_events", Integer, nullable=False, default=0),
            Column("governance_flags", Integer, nullable=False, default=0),
            Column("fulfillment_rate", Numeric),
            Column("discrepancy_frequency", Numeric),
            Column("receipt_to_dispatch_cycle_time_h", Numeric),
            Column("events_considered", Integer, nullable=False, default=0),
            Column("pipeline_run_id", String(36), nullable=False),
            Column("computed_at", DateTime(timezone=True), nullable=False),
        ]

    Table(
        FACT_TABLE,
        metadata,
        Column("iso_week", String(8), primary_key=True),
        Column("warehouse", String(8), primary_key=True),
        Column("client_id", String(255), primary_key=True),
        *_value_columns(),
    )
    Table(
        STAGING_TABLE,
        metadata,
        Column("iso_week", String(8)),
        Column("warehouse", String(8)),
        Column("client_id", String(255)),
        *_value_columns(),
    )

    Table(
        DIM_SKU_TABLE,
        metadata,
        Column("sku_id", Integer, primary_key=True),
        Column("sku", String(64), nullable=False),
        Column("name", String(255)),
        Column("client_name", String(255)),
        Column("category", String(64)),
        Column("warehouse", String(8)),
        Column("is_current", Integer, nullable=False, default=1),
        Column("seen_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        RUNS_TABLE,
        metadata,
        Column("run_id", String(36), primary_key=True),
        Column("pipeline_name", String(128), nullable=False),
        Column("pipeline_version", String(32), nullable=False),
        Column("trigger", String(16), nullable=False),
        Column("triggered_by", String(64)),
        Column("window_from", DateTime(timezone=True), nullable=False),
        Column("window_to", DateTime(timezone=True), nullable=False),
        Column("iso_week", String(8), nullable=False),
        Column("sku_snapshot_rows", Integer),
        Column("sku_rows_deactivated", Integer),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("finished_at", DateTime(timezone=True)),
        Column("status", String(16), nullable=False),
        Column("rows_read", Integer),
        Column("rows_rejected", Integer),
        Column("rows_unmatched_sku", Integer),
        Column("rows_transformed", Integer),
        Column("rows_upserted_insert", Integer),
        Column("rows_upserted_update", Integer),
        Column("error_count", Integer),
        Column("error_message", String),
        Column("error_sample", String),
    )

    return metadata
