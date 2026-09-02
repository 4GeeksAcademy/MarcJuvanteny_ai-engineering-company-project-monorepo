"""Extraccion (Fase 2.2 / 4.1 del diseno): solo lectura, sin logica de KPI.

Funciones planas (sin decorador de Prefect: flow.py las envuelve en @task).
Cada una hace un unico SELECT y devuelve un DataFrame crudo, sin normalizar.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import Engine, bindparam, text

from .config import INVENTORY_EVENT_TYPES

TELEMETRY_EVENTS_COLUMNS = (
    "event_id",
    "timestamp",
    "session_id",
    "user_id",
    "event_type",
    "schema_version",
    "request_id",
    "properties",
)

SKU_COLUMNS = ("id", "name", "sku", "client_name", "category", "warehouse")


def extract_inventory_events(engine: Engine, week_start: datetime, week_end: datetime) -> pd.DataFrame:
    """Eventos de los 5 event_type de inventario en [week_start, week_end).

    `week_start`/`week_end` ya incluyen la ventana de gracia (Fase 2.4): el
    llamador decide cuanto historial reprocesar, esta funcion solo filtra.
    """
    query = text(
        f"SELECT {', '.join(TELEMETRY_EVENTS_COLUMNS)} FROM telemetry_events "
        "WHERE timestamp >= :start AND timestamp < :end "
        "AND event_type IN :event_types"
    ).bindparams(bindparam("event_types", expanding=True))
    with engine.connect() as connection:
        return pd.read_sql(
            query,
            connection,
            params={"start": week_start, "end": week_end, "event_types": list(INVENTORY_EVENT_TYPES)},
        )


def extract_sku_snapshot(engine: Engine) -> pd.DataFrame:
    """Snapshot completo de la tabla SKU (sin updated_at -> no hay incremental fiable)."""
    query = text(f"SELECT {', '.join(SKU_COLUMNS)} FROM sku")
    with engine.connect() as connection:
        return pd.read_sql(query, connection)
