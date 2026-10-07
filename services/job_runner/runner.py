"""Crear, actualizar y consultar `ops.job_runs`.

Capa de control de estado reutilizable por cualquier script (hoy solo
`scripts/nightly_export.py`, pero no es especifico de ese job: cualquier
`job_name` nuevo usa las mismas funciones). Sin dependencia de Prefect ni de
un `job_name` hardcodeado dentro del modulo.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from config import JOB_RUNS_SCHEMA, JOB_RUNS_TABLE
from schema import build_metadata


class JobLockHeldError(RuntimeError):
    """Ya hay una corrida `processing` para este `job_name` (constraint de `schema.py`)."""


def _table_name(schema: str) -> str:
    return f"{schema}.{JOB_RUNS_TABLE}" if schema else JOB_RUNS_TABLE


def ensure_schema(engine: Engine, schema: str = JOB_RUNS_SCHEMA) -> None:
    """Crea el esquema (si aplica) y la tabla + indices si no existen. Idempotente."""
    if schema and engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    build_metadata(schema).create_all(engine, checkfirst=True)


def has_processing_lock(engine: Engine, job_name: str, schema: str = JOB_RUNS_SCHEMA) -> bool:
    """True si ya hay una fila `processing` para `job_name` (cualquier `target_date`).

    Chequeo rapido/legible antes de intentar `start_job_run()`. No es en si
    mismo el mecanismo que evita la condicion de carrera entre dos corridas
    casi simultaneas -- eso lo hace el indice unico parcial de `schema.py`,
    que `start_job_run()` deja que falle y traduce a `JobLockHeldError`.
    """
    query = text(f"SELECT 1 FROM {_table_name(schema)} WHERE job_name = :job_name AND status = 'processing' LIMIT 1")
    with engine.connect() as connection:
        return connection.execute(query, {"job_name": job_name}).first() is not None


def has_completed_for_date(engine: Engine, job_name: str, target_date: date, schema: str = JOB_RUNS_SCHEMA) -> bool:
    """True si ya existe una corrida `completed` para `(job_name, target_date)`.

    Clave de idempotencia: `job_name` solo no alcanza (un job corre todos los
    dias), hace falta `target_date` (Fase "Idempotencia y bloqueo" de la
    guia).
    """
    query = text(
        f"SELECT 1 FROM {_table_name(schema)} WHERE job_name = :job_name AND target_date = :target_date "
        "AND status = 'completed' LIMIT 1"
    )
    with engine.connect() as connection:
        return connection.execute(query, {"job_name": job_name, "target_date": target_date}).first() is not None


def start_job_run(engine: Engine, job_name: str, target_date: date, schema: str = JOB_RUNS_SCHEMA) -> str:
    """Inserta la fila `processing`. Devuelve `id`.

    Lanza `JobLockHeldError` si otra corrida gano la carrera entre
    `has_processing_lock()` y este INSERT (constraint de `schema.py`) -- el
    llamador debe tratarlo igual que un `has_processing_lock()` que dio
    `True`: abortar sin marcar `failed`, esto no es un error del job.
    """
    metadata = build_metadata(schema)
    table = metadata.tables[_table_name(schema)]
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    try:
        with engine.begin() as connection:
            connection.execute(
                table.insert(),
                {
                    "id": run_id,
                    "job_name": job_name,
                    "target_date": target_date,
                    "status": "processing",
                    "started_at": now,
                    "created_at": now,
                },
            )
    except IntegrityError as exc:
        raise JobLockHeldError(f"Ya hay una corrida 'processing' para el job '{job_name}'.") from exc

    return run_id


def _close(engine: Engine, run_id: str, *, status: str, error_message: str | None, schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"UPDATE {_table_name(schema)} SET status = :status, finished_at = :finished_at, "
                "error_message = :error_message WHERE id = :id"
            ),
            {"status": status, "finished_at": datetime.now(timezone.utc), "error_message": error_message, "id": run_id},
        )


def mark_completed(engine: Engine, run_id: str, schema: str = JOB_RUNS_SCHEMA) -> None:
    _close(engine, run_id, status="completed", error_message=None, schema=schema)


def mark_failed(engine: Engine, run_id: str, error_message: str, schema: str = JOB_RUNS_SCHEMA) -> None:
    _close(engine, run_id, status="failed", error_message=error_message, schema=schema)


def get_latest_job_run(engine: Engine, job_name: str, schema: str = JOB_RUNS_SCHEMA) -> dict[str, Any] | None:
    """Ultima corrida (por `created_at`) de `job_name`, o None si no hay ninguna."""
    query = text(f"SELECT * FROM {_table_name(schema)} WHERE job_name = :job_name ORDER BY created_at DESC LIMIT 1")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_name": job_name}).mappings().first()
    return dict(row) if row else None
