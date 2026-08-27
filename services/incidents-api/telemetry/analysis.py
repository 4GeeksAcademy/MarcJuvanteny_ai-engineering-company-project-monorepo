"""Pipeline de analisis de telemetria (Pandas).

Funciones de metrica puras sobre dimensiones tecnicas/operacionales del
catalogo de eventos (`telemetry-plan.md` / `event-shcemas.json`): volumen,
errores, latencia y disponibilidad. Deliberadamente NO se calculan metricas
de negocio (ventas, conversion, ingresos) — eso corresponde al Hito de Data
Pipelines.

Cada funcion de metrica recibe el DataFrame completo de eventos y la ventana
[start_date, end_date) ya resuelta por el llamador (no aplican su propia
ventana por defecto), filtra internamente por esa ventana y no muta el
DataFrame recibido ni ningun estado externo: llamarlas dos veces con los
mismos argumentos produce siempre el mismo resultado.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

# Event types que representan un fallo tecnico/operacional, usados por
# compute_error_rate. No incluye eventos de negocio (inventario) ni de
# navegacion — solo fallos del propio sistema.
ERROR_EVENT_TYPES = frozenset(
    {
        "api_request_failed",
        "auth_login_failed",
        "frontend_error_captured",
    }
)

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


def load_events(engine: Engine, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Carga en un DataFrame las filas de telemetry_events dentro de [start_date, end_date).

    No es una funcion de metrica (hace I/O), es la entrada del pipeline.
    """
    query = (
        f"select {', '.join(TELEMETRY_EVENTS_COLUMNS)} "
        "from telemetry_events where timestamp >= %(start)s and timestamp < %(end)s"
    )
    return pd.read_sql(query, engine, params={"start": start_date, "end": end_date})


def _events_in_window(events: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Filtro comun (vectorizado, sin loops) reutilizado por cada funcion de metrica."""
    if events.empty:
        return events
    timestamps = pd.to_datetime(events["timestamp"], utc=True)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    return events.loc[(timestamps >= start) & (timestamps < end)]


def _latency_properties(events: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Devuelve las properties de los api_latency_recorded en la ventana, ya normalizadas a columnas."""
    window = _events_in_window(events, start_date, end_date)
    latency_events = window.loc[window["event_type"] == "api_latency_recorded"]
    if latency_events.empty:
        return pd.DataFrame(columns=["endpoint", "method", "status_code", "latency_ms", "service"])
    return pd.json_normalize(latency_events["properties"].tolist())


def compute_event_volume(events: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    """Dimension: volumen. Numero de eventos por event_type en la ventana."""
    window = _events_in_window(events, start_date, end_date)
    if window.empty:
        return {"total_events": 0, "by_event_type": {}}
    by_type = window.groupby("event_type").size()
    return {
        "total_events": int(by_type.sum()),
        "by_event_type": by_type.sort_values(ascending=False).to_dict(),
    }


def compute_error_rate(events: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    """Dimension: errores. Conteo y tasa de eventos de fallo tecnico sobre el total de eventos."""
    window = _events_in_window(events, start_date, end_date)
    total_events = len(window)
    if total_events == 0:
        return {"total_events": 0, "error_events": 0, "error_rate": 0.0, "by_event_type": {}}

    error_mask = window["event_type"].isin(ERROR_EVENT_TYPES)
    error_events = window.loc[error_mask]
    by_type = error_events.groupby("event_type").size()
    return {
        "total_events": int(total_events),
        "error_events": int(len(error_events)),
        "error_rate": round(len(error_events) / total_events, 4),
        "by_event_type": by_type.to_dict(),
    }


def compute_latency_percentiles(events: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    """Dimension: latencia. p50/p95/p99 y media de latency_ms por endpoint (api_latency_recorded)."""
    properties = _latency_properties(events, start_date, end_date)
    if properties.empty:
        return {"sample_size": 0, "by_endpoint": {}}

    stats = properties.groupby("endpoint")["latency_ms"].agg(
        count="count",
        mean_ms="mean",
        p50_ms=lambda values: values.quantile(0.50),
        p95_ms=lambda values: values.quantile(0.95),
        p99_ms=lambda values: values.quantile(0.99),
    )
    return {
        "sample_size": int(len(properties)),
        "by_endpoint": stats.round(2).to_dict(orient="index"),
    }


def compute_availability(events: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    """Dimension: disponibilidad. % de respuestas no-5xx sobre las llamadas medidas, por endpoint."""
    properties = _latency_properties(events, start_date, end_date)
    if properties.empty:
        return {"sample_size": 0, "overall_availability_pct": None, "by_endpoint": {}}

    is_available = properties["status_code"] < 500
    by_endpoint = is_available.groupby(properties["endpoint"]).mean()
    return {
        "sample_size": int(len(properties)),
        "overall_availability_pct": round(float(is_available.mean()) * 100, 2),
        "by_endpoint": (by_endpoint * 100).round(2).to_dict(),
    }
