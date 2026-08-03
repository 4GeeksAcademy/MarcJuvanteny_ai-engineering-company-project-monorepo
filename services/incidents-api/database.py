from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_TINYDB_PATH = SERVICE_DIR / "suppliers.json"

load_dotenv(SERVICE_DIR / ".env")


def get_tinydb_path() -> Path:
    raw_path = os.environ.get("TINYDB_PATH")
    return Path(raw_path) if raw_path else DEFAULT_TINYDB_PATH


def get_supabase_database_url() -> str:
    database_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_DATABASE_URL (or DATABASE_URL) is not configured.")
    return database_url


@lru_cache(maxsize=1)
def get_sql_engine():
    return create_engine(get_supabase_database_url(), pool_pre_ping=True)


SQL_ENGINE = get_sql_engine()


def get_db() -> Generator[Session, None, None]:
    with Session(get_sql_engine()) as session:
        yield session
