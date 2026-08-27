from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import insert
from sqlmodel import Session

from database import SQL_ENGINE, get_db
from models import TelemetryEventRecord
from telemetry.analysis import (
    compute_availability,
    compute_error_rate,
    compute_event_volume,
    compute_latency_percentiles,
    load_events,
)

# Ventana por defecto del reporte cuando no se especifican start_date/end_date.
DEFAULT_REPORT_WINDOW = timedelta(days=7)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
logger = logging.getLogger("telemetry")

# Reserved for forwarding validated events to an external analytics/warehouse
# sink. Not used yet — establishing the config pattern ahead of that phase.
TELEMETRY_FORWARD_ENDPOINT = os.environ.get("TELEMETRY_ENDPOINT")


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventId: str
    timestamp: str
    sessionId: str
    userId: str
    event_type: str
    schemaVersion: str
    requestId: str
    properties: dict[str, Any]


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Raw, unvalidated event payloads — kept loose here so one malformed event
    # can't fail FastAPI's request-body validation and reject the whole batch.
    # Each item is validated individually against TelemetryEvent below.
    events: list[dict[str, Any]]


class TelemetryIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received: int
    stored: int
    rejected: int


def _parse_valid_event(raw_event: dict[str, Any]) -> TelemetryEvent | None:
    try:
        event = TelemetryEvent.model_validate(raw_event)
        datetime.fromisoformat(event.timestamp)
    except (ValidationError, ValueError, TypeError):
        return None
    return event


def _event_to_row(event: TelemetryEvent) -> dict[str, Any]:
    return {
        "event_id": event.eventId,
        "timestamp": datetime.fromisoformat(event.timestamp),
        "session_id": event.sessionId,
        "user_id": event.userId,
        "event_type": event.event_type,
        "schema_version": event.schemaVersion,
        "request_id": event.requestId,
        "properties": event.properties,
    }


@router.post("/events", response_model=TelemetryIngestResponse, status_code=status.HTTP_200_OK)
async def ingest_telemetry_events(
    payload: TelemetryBatch,
    db: Session = Depends(get_db),
) -> TelemetryIngestResponse:
    valid_events = [event for raw in payload.events if (event := _parse_valid_event(raw)) is not None]
    rejected_count = len(payload.events) - len(valid_events)

    counts_by_event_type = Counter(event.event_type for event in valid_events)
    logger.info(
        "Received %d telemetry event(s), %d stored, %d rejected: %s",
        len(payload.events),
        len(valid_events),
        rejected_count,
        dict(counts_by_event_type),
    )

    if valid_events:
        rows = [_event_to_row(event) for event in valid_events]
        db.execute(insert(TelemetryEventRecord), rows)
        db.commit()

    return TelemetryIngestResponse(
        received=len(payload.events),
        stored=len(valid_events),
        rejected=rejected_count,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/report")
async def get_telemetry_report(
    start_date: datetime | None = Query(default=None, description="ISO 8601. Por defecto: end_date - 7 dias."),
    end_date: datetime | None = Query(default=None, description="ISO 8601. Por defecto: ahora (UTC)."),
) -> dict[str, Any]:
    # El periodo se resuelve una unica vez aqui y se pasa igual a cada
    # funcion de metrica — ninguna aplica su propia ventana por defecto.
    resolved_end = _as_utc(end_date) if end_date is not None else datetime.now(timezone.utc)
    resolved_start = _as_utc(start_date) if start_date is not None else resolved_end - DEFAULT_REPORT_WINDOW

    events = load_events(SQL_ENGINE, resolved_start, resolved_end)

    return {
        "period": {"from": resolved_start.isoformat(), "to": resolved_end.isoformat()},
        "metrics": {
            "volume": compute_event_volume(events, resolved_start, resolved_end),
            "errors": compute_error_rate(events, resolved_start, resolved_end),
            "latency": compute_latency_percentiles(events, resolved_start, resolved_end),
            "availability": compute_availability(events, resolved_start, resolved_end),
        },
    }
