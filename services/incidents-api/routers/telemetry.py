from __future__ import annotations

import logging
import os
from collections import Counter
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

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

    events: list[TelemetryEvent]


class TelemetryIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received: int


@router.post("/events", response_model=TelemetryIngestResponse, status_code=status.HTTP_200_OK)
async def ingest_telemetry_events(payload: TelemetryBatch) -> TelemetryIngestResponse:
    counts_by_event_type = Counter(event.event_type for event in payload.events)
    logger.info(
        "Received %d telemetry event(s): %s",
        len(payload.events),
        dict(counts_by_event_type),
    )
    return TelemetryIngestResponse(received=len(payload.events))
