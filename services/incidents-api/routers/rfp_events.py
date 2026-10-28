"""Stream SSE de tickets de RFP nuevos (`CONTEXT/CONTEXT10.md`, Hito 10
Parte 1) -- `GET /rfp/events`.

Wire (un evento por ticket que entra con `status = analizando`):

    id: 42
    event: rfp_ticket_created
    data: {"ticket_id": 17, "rfp_id": 9, "client_name": "...", ...}

- Evento con nombre explícito (`rfp_ticket_created`), nunca el genérico
  `message`; `data:` es SOLO el payload del ticket, sin sobre anidado.
- `id:` es el id del outbox (`rfp_intake/events.py::RFPTicketEvent`), así
  que el cliente reconecta con `Last-Event-ID: <último id visto>` y este
  endpoint le reenvía todo lo que se perdió (replay desde Postgres).
  Sin `Last-Event-ID`, el stream empieza en "ahora" -- el estado previo lo
  carga la UI con `GET /rfp/tickets`, no el stream -- y el frame de
  apertura ya le entrega ese cursor (`id:` sin `data:`).
- Keep-alive: un frame de comentario (`: keep-alive`) cada
  `keepalive_seconds` sin eventos, para que proxies/navegador no cierren
  la conexión por inactividad.

Ruta propia (`/rfp/events`, no `/rfp/tickets/stream`): `routers/rfp.py` ya
tiene `GET /rfp/tickets/{ticket_id}` con `ticket_id: int`, que capturaría
`/stream` y devolvería 422. Módulo propio también para no arrastrar Celery
ni el grafo de LangGraph a un endpoint que solo lee una tabla.

Autenticado con el MISMO JWT que el resto del backoffice
(`auth_service.get_user_from_token`, mismo patrón que
`routers/rfp.py::get_current_rfp_user`): sin `Authorization: Bearer` válido
la respuesta es 401 y nunca se abre el stream.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlmodel import Session

from auth_service import get_user_from_token
from database import get_tinydb_path
from models import UserWithProfileRecord

import rfp_pipeline_path  # noqa: F401
from rfp_intake.events import RFPTicketEvent, fetch_events_after, latest_event_id
from rfp_intake.models import get_sql_engine

router = APIRouter(prefix="/rfp", tags=["rfp"])
bearer_scheme = HTTPBearer(auto_error=False)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # nginx/proxies: no bufferizar, si no los eventos llegan en bloque.
    "X-Accel-Buffering": "no",
}


@dataclass(frozen=True)
class StreamSettings:
    poll_interval_seconds: float = 1.0
    keepalive_seconds: float = 15.0
    # Sugerencia al cliente para el primer reintento (campo `retry:` de SSE).
    # La UI usa su propio backoff progresivo encima de esto.
    retry_ms: int = 2000
    # Solo para tests: corta el stream tras N ciclos de polling. En
    # producción el stream vive hasta que el cliente se desconecta.
    max_polls: int | None = None


def get_stream_settings() -> StreamSettings:
    return StreamSettings()


def get_rfp_events_engine() -> Engine:
    return get_sql_engine()


def get_current_stream_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserWithProfileRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"}
        )
    return get_user_from_token(get_tinydb_path(), credentials.credentials)


def format_sse_event(event: RFPTicketEvent) -> str:
    data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.id}\nevent: {event.event_type}\ndata: {data}\n\n"


def _parse_last_event_id(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        # Un Last-Event-ID que no generó este servidor no puede ubicar un
        # punto de replay -- se trata como conexión nueva.
        return None


def _read_cursor(engine: Engine) -> int:
    with Session(engine) as session:
        return latest_event_id(session)


def _read_events(engine: Engine, after_id: int) -> list[RFPTicketEvent]:
    with Session(engine) as session:
        events = fetch_events_after(session, after_id)
        for event in events:
            session.expunge(event)
        return events


async def _event_stream(
    request: Request, engine: Engine, last_event_id: int | None, settings: StreamSettings
) -> AsyncIterator[str]:
    cursor = last_event_id if last_event_id is not None else await asyncio.to_thread(_read_cursor, engine)

    # Frame de apertura sin `data:` (no dispara evento en el cliente) pero con
    # `id:` = cursor actual: así el cliente tiene un Last-Event-ID válido
    # aunque se caiga ANTES de recibir su primer evento, y el replay al
    # reconectar cubre también ese hueco.
    yield f"retry: {settings.retry_ms}\nid: {cursor}\n: connected\n\n"

    last_sent_at = monotonic()
    polls = 0
    while True:
        if await request.is_disconnected():
            return

        events = await asyncio.to_thread(_read_events, engine, cursor)
        for event in events:
            yield format_sse_event(event)
            cursor = event.id
        if events:
            last_sent_at = monotonic()
        elif monotonic() - last_sent_at >= settings.keepalive_seconds:
            yield ": keep-alive\n\n"
            last_sent_at = monotonic()

        polls += 1
        if settings.max_polls is not None and polls >= settings.max_polls:
            return
        await asyncio.sleep(settings.poll_interval_seconds)


@router.get("/events")
async def stream_rfp_events(
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    current_user: UserWithProfileRecord = Depends(get_current_stream_user),
    engine: Engine = Depends(get_rfp_events_engine),
    settings: StreamSettings = Depends(get_stream_settings),
) -> StreamingResponse:
    _ = current_user
    return StreamingResponse(
        _event_stream(request, engine, _parse_last_event_id(last_event_id), settings),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
