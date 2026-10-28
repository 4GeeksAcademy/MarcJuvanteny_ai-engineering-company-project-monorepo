"""Outbox de eventos en tiempo real del flujo de RFPs (`CONTEXT/CONTEXT10.md`,
Hito 10 Parte 1: "notificación en tiempo real cuando un ticket nuevo entra
al sistema con status = analizando").

Por qué un outbox en Postgres y no un pub/sub en memoria: el evento nace en
el worker de Celery (`pipeline.py::process_rfp_ticket`, otro proceso) y lo
consume el endpoint SSE de `services/incidents-api` -- un `asyncio.Queue`
del proceso de FastAPI nunca lo vería. Escribirlo en la misma base, en la
misma transacción que el `RFPMetadataRecord`, además da:

- `id` autoincremental = `id:` del wire SSE = `Last-Event-ID` del cliente:
  el replay tras una caída es solo `WHERE id > last_event_id`.
- Nunca un evento de un ticket cuya metadata no se persistió (o al revés).

Los nombres de campo del payload son EXACTAMENTE los del sistema de RFPs
ya existente (`models.py`: `RFPTicket`, `RFPMetadataRecord`), tal como pide
CONTEXT10.md §5 -- incluido el valor real del estado (`"analizando"`, el
enum de CONTEXT9.md §2.3 que persiste este sistema), nunca un sinónimo
nuevo inventado solo para el evento.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, select

from .models import RFPMetadataRecord, RFPTicket

RFP_TICKET_CREATED = "rfp_ticket_created"


class RFPTicketEvent(SQLModel, table=True):
    """Append-only. `payload` es un snapshot del ticket en el momento del
    evento (no una referencia viva): el estado del ticket sigue avanzando
    después, el evento describe lo que pasó en ese instante."""

    __tablename__ = "rfp_ticket_events"

    id: int | None = SQLField(default=None, primary_key=True)
    event_type: str = SQLField(index=True)
    ticket_id: int = SQLField(foreign_key="rfp_tickets.id", index=True)
    # JSONB en Postgres (como el resto de `models.py`), JSON genérico en
    # cualquier otro motor -- los tests del endpoint SSE corren en SQLite.
    payload: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    )
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


def _isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_ticket_created_payload(ticket: RFPTicket, metadata: RFPMetadataRecord) -> dict[str, Any]:
    """Solo lo suficiente para que Ventas sepa qué llegó (CONTEXT10.md §3) --
    nunca el documento completo ni las secciones por departamento.
    `rfp_id` es el id del `RFPMetadataRecord` (la entidad "RFP" 1:1 con el
    ticket en este sistema)."""

    return {
        "ticket_id": ticket.id,
        "rfp_id": metadata.id,
        "client_name": metadata.client_name,
        "client_country": metadata.client_country,
        "services_requested": list(metadata.services_requested or []),
        "status": ticket.status,
        "created_at": _isoformat_utc(ticket.created_at),
    }


def record_ticket_created(session: Session, ticket: RFPTicket, metadata: RFPMetadataRecord) -> RFPTicketEvent:
    """Agrega el evento a la sesión SIN commitear -- el caller lo commitea en
    la misma transacción que la metadata (outbox). Idempotente por ticket:
    reprocesar un ticket (`scripts/rfp_reprocess.py --ticket-id`) nunca
    emite un segundo `rfp_ticket_created` para el mismo `ticket_id`."""

    existing = session.exec(
        select(RFPTicketEvent).where(
            RFPTicketEvent.ticket_id == ticket.id, RFPTicketEvent.event_type == RFP_TICKET_CREATED
        )
    ).first()
    if existing is not None:
        return existing

    event = RFPTicketEvent(
        event_type=RFP_TICKET_CREATED,
        ticket_id=ticket.id,
        payload=build_ticket_created_payload(ticket, metadata),
    )
    session.add(event)
    return event


def fetch_events_after(session: Session, after_id: int, limit: int = 100) -> list[RFPTicketEvent]:
    return list(
        session.exec(
            select(RFPTicketEvent).where(RFPTicketEvent.id > after_id).order_by(RFPTicketEvent.id).limit(limit)
        ).all()
    )


def latest_event_id(session: Session) -> int:
    return session.exec(select(func.max(RFPTicketEvent.id))).one() or 0
