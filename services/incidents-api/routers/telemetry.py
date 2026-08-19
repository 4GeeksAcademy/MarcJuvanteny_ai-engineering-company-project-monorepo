from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import insert
from sqlmodel import Session

from database import get_db
from models import TelemetryEventRecord

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
