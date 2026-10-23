"""Punto de entrada único del flujo de recepción de RFPs -- lo que
`services/incidents-api` (el backend existente, ver `CONTEXT9.md` Sección
2.4: "sin un proceso API nuevo") y `scripts/` (reproceso manual, smoke
runs) llaman. Orquesta, en orden: conversión PDF -> Markdown
(`pdf_conversion.py`), el grafo clasificador-orquestador-workers-synthesizer
(`graph.py`), y la persistencia en PostgreSQL (`models.py`) -- el router de
`services/incidents-api` solo dispara esto, nunca contiene lógica de
agentes (`CONTEXT9.md`: "los routers importan y disparan; no poseen la
lógica de agentes").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from .graph import build_graph
from .models import RFPDepartmentSection, RFPMetadataRecord, RFPTicket, TicketStatus, get_sql_engine
from .pdf_conversion import compute_readability_metrics, convert_pdf_to_markdown

logger = logging.getLogger("rfp_intake")

_COMPILED_GRAPH = build_graph()


def process_rfp_ticket(ticket_id: int, *, session: Session | None = None) -> dict[str, Any]:
    """Procesa un ticket ya creado en estado `analizando` (ver
    `RFPTicket.raw_pdf_path`): convierte su PDF, corre el grafo, y
    persiste metadatos/key_aspects/estado final. Nunca deja el ticket
    colgado en `analizando` -- cualquier excepción durante el proceso
    también se captura y el ticket pasa a `descartado` con el motivo real
    del fallo (`CONTEXT9.md`: "no falles en silencio" aplica también a
    errores de infraestructura, no solo a clasificación).

    Devuelve el resultado completo del grafo (útil para `scripts/` y
    tests) -- el caller HTTP no necesita este valor de retorno, solo que
    el ticket haya quedado en el estado correcto en la base.
    """

    owns_session = session is None
    active_session = session or Session(get_sql_engine())

    try:
        ticket = active_session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise ValueError(f"RFPTicket {ticket_id} no existe.")

        try:
            markdown_text = convert_pdf_to_markdown(ticket.raw_pdf_path)
            readability_metrics = compute_readability_metrics(markdown_text)
            graph_result = _COMPILED_GRAPH.invoke({"markdown_text": markdown_text})
        except Exception as exc:
            logger.exception("Fallo procesando RFPTicket %s", ticket_id)
            ticket.status = TicketStatus.DESCARTADO.value
            ticket.discard_reason = f"Error de procesamiento: {exc}"
            ticket.updated_at = datetime.now(timezone.utc)
            active_session.add(ticket)
            active_session.commit()
            return {"ticket_id": ticket_id, "status": ticket.status, "error": str(exc)}

        classification = graph_result.get("classification") or {}

        if not classification.get("is_valid"):
            ticket.status = TicketStatus.DESCARTADO.value
            ticket.discard_reason = classification.get("reason", "Documento no identificado como RFP.")
            ticket.updated_at = datetime.now(timezone.utc)
            active_session.add(ticket)
            active_session.commit()
            return {"ticket_id": ticket_id, "status": ticket.status, "classification": classification}

        metadata = graph_result.get("metadata") or {}
        metadata_record = RFPMetadataRecord(
            ticket_id=ticket_id,
            client_name=metadata.get("client_name"),
            client_country=metadata.get("client_country"),
            services_requested=metadata.get("services_requested") or [],
            monthly_volume=metadata.get("monthly_volume"),
            deadline=metadata.get("deadline"),
            budget_range=metadata.get("budget_range"),
            departments_needed=metadata.get("departments_needed") or [],
            readability_metrics=readability_metrics,
        )
        active_session.add(metadata_record)

        summary = graph_result.get("summary") or {}
        key_aspects_by_department: dict[str, Any] = summary.get("key_aspects_by_department", {})
        for department_id, key_aspects in key_aspects_by_department.items():
            active_session.add(
                RFPDepartmentSection(ticket_id=ticket_id, department_id=department_id, key_aspects=key_aspects)
            )

        ticket.status = TicketStatus.ANALISIS_COMPLETO.value
        ticket.updated_at = datetime.now(timezone.utc)
        active_session.add(ticket)
        active_session.commit()

        return {
            "ticket_id": ticket_id,
            "status": ticket.status,
            "classification": classification,
            "metadata": metadata,
            "summary": summary,
        }
    finally:
        if owns_session:
            active_session.close()


def get_ticket_with_metadata(ticket_id: int, *, session: Session | None = None) -> dict[str, Any] | None:
    """Usado por el endpoint de status (`GET /rfp/tickets/{id}`, Parte 1 --
    "la UI consulta/refresca estado") -- ticket + metadata + secciones ya
    persistidas, sin volver a correr nada."""

    owns_session = session is None
    active_session = session or Session(get_sql_engine())

    try:
        ticket = active_session.get(RFPTicket, ticket_id)
        if ticket is None:
            return None

        metadata = active_session.exec(
            select(RFPMetadataRecord).where(RFPMetadataRecord.ticket_id == ticket_id)
        ).first()
        sections = active_session.exec(
            select(RFPDepartmentSection).where(RFPDepartmentSection.ticket_id == ticket_id)
        ).all()

        return {
            "ticket": ticket.model_dump(),
            "metadata": metadata.model_dump() if metadata else None,
            "sections": [section.model_dump() for section in sections],
        }
    finally:
        if owns_session:
            active_session.close()
