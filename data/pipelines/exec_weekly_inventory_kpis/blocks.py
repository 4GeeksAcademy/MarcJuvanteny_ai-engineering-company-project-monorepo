"""Resolucion de configuracion y credenciales (Fase 4.2 del diseno).

Intenta cargar Prefect blocks por nombre (`trackflow-supabase`,
`reporting-pipeline-config`); si no hay Prefect server/Cloud configurado (caso
tipico en desarrollo local o CI), cae a variables de entorno / defaults.
Nunca se hardcodean credenciales.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

from .config import DEFAULT_PIPELINE_CONFIG

PACKAGE_DIR = Path(__file__).resolve().parent
PIPELINES_DIR = PACKAGE_DIR.parent

load_dotenv(PIPELINES_DIR / ".env")

SUPABASE_BLOCK_NAME = "trackflow-supabase"
CONFIG_BLOCK_NAME = "reporting-pipeline-config"


def _database_url_from_env() -> str:
    database_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "No hay conexion a Supabase configurada. Define SUPABASE_DATABASE_URL "
            f"(o DATABASE_URL) en data/pipelines/.env, o crea el block "
            f"SqlAlchemyConnector '{SUPABASE_BLOCK_NAME}' con `prefect block register`."
        )
    return database_url


def get_database_url() -> str:
    """Connection string de Supabase: Prefect block si existe, si no env var."""
    try:
        from prefect_sqlalchemy import SqlAlchemyConnector  # type: ignore[import-not-found]

        connector = SqlAlchemyConnector.load(SUPABASE_BLOCK_NAME)
        return str(connector.connection_info.url)
    except Exception:
        return _database_url_from_env()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


def get_pipeline_config() -> dict:
    """Parametros no secretos del pipeline: block JSON/Variable si existe, si no defaults."""
    try:
        from prefect.variables import Variable  # type: ignore[import-not-found]

        value = Variable.get("reporting_pipeline_config")
        if value:
            return {**DEFAULT_PIPELINE_CONFIG, **dict(value)}
    except Exception:
        pass
    return dict(DEFAULT_PIPELINE_CONFIG)
