"""Metadata SQLAlchemy Core de `ops.job_runs`.

Fuente de verdad ejecutable para `ensure_schema()` (create_all, portable
Postgres/SQLite para tests). `schema.sql` es el DDL Postgres equivalente para
`psql`/migracion (mismo patron que `data/pipelines/exec_weekly_inventory_kpis/schema.py`).
"""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Index, MetaData, String, Table, text

from config import JOB_RUNS_SCHEMA, JOB_RUNS_TABLE


def build_metadata(schema: str = JOB_RUNS_SCHEMA) -> MetaData:
    metadata = MetaData(schema=schema or None)

    Table(
        JOB_RUNS_TABLE,
        metadata,
        Column("id", String(36), primary_key=True),
        Column("job_name", String(128), nullable=False),
        Column("target_date", Date, nullable=False),
        Column("status", String(16), nullable=False),
        Column("started_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("error_message", String),
        Column("created_at", DateTime(timezone=True), nullable=False),
        # Idempotencia por dia: consultas por (job_name, target_date) -- ver
        # has_completed_for_date() en runner.py.
        Index(f"ix_{JOB_RUNS_TABLE}_job_name_target_date", "job_name", "target_date"),
        # El lock real (no solo el chequeo previo has_processing_lock() en
        # runner.py): a lo sumo una fila "processing" por job_name a la vez.
        # Un segundo INSERT concurrente con status="processing" para el
        # mismo job_name viola esta constraint -> IntegrityError -> se
        # traduce a JobLockHeldError en runner.py. No hace falta tabla o
        # columna de lock aparte, es un indice unico parcial sobre la misma
        # tabla.
        Index(
            f"ux_{JOB_RUNS_TABLE}_processing_lock",
            "job_name",
            unique=True,
            postgresql_where=text("status = 'processing'"),
            sqlite_where=text("status = 'processing'"),
        ),
    )

    return metadata
