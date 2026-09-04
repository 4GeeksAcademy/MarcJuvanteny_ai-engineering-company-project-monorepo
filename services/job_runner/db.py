"""Conexion a la misma base que `telemetry_events`/`sku` (Supabase).

Mismo patron que `services/incidents-api/database.py` y
`data/pipelines/exec_weekly_inventory_kpis/blocks.py`: lee
`SUPABASE_DATABASE_URL` (o `DATABASE_URL`) de `.env`. Sin dependencia de
Prefect (a diferencia de `blocks.py`): `job_runner` lo usa un script de cron
plano, no un flow.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

PACKAGE_DIR = Path(__file__).resolve().parent
load_dotenv(PACKAGE_DIR / ".env")


def _database_url_from_env() -> str:
    database_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "No hay conexion a Supabase configurada. Define SUPABASE_DATABASE_URL "
            "(o DATABASE_URL) en services/job_runner/.env."
        )
    return database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(_database_url_from_env(), pool_pre_ping=True)
