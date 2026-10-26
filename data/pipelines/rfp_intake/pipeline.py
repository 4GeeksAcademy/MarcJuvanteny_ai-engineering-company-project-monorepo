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

from .evaluation_graph import build_evaluation_graph
from .generation_graph import build_generation_graph
from .generators import GENERATOR_REGISTRY
from .graph import build_graph
from .models import RFPDepartmentSection, RFPMetadataRecord, RFPTicket, TicketStatus, get_sql_engine
from .pdf_conversion import compute_readability_metrics, convert_pdf_to_markdown

logger = logging.getLogger("rfp_intake")

_COMPILED_GRAPH = build_graph()
_COMPILED_GENERATION_GRAPH = build_generation_graph()
_COMPILED_EVALUATION_GRAPH = build_evaluation_graph()

# CONTEXT9.md, "Métricas de negocio": "Iteraciones promedio por sección en
# el ciclo generador-evaluador (ideal: menos de 2)" -- un tope de 3 (el
# intento inicial + 2 reintentos con feedback) deja margen holgado sobre
# ese ideal sin permitir un ciclo indefinido.
MAX_GENERATION_ITERATIONS = 3


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


def _evaluate_draft(department_id: str, client_country: str | None, key_aspects: dict, draft_content: str) -> dict:
    evaluation_state = {
        "department_id": department_id,
        "client_country": client_country,
        "key_aspects": key_aspects,
        "draft_content": draft_content,
    }
    return _COMPILED_EVALUATION_GRAPH.invoke(evaluation_state)["evaluation_result"]


def _generate_and_evaluate_with_retries(
    department_id: str,
    client_country: str | None,
    key_aspects: dict,
    initial_draft: str,
    *,
    generator_fn=None,
    evaluate_fn=_evaluate_draft,
    max_iterations: int = MAX_GENERATION_ITERATIONS,
) -> tuple[str, dict, bool]:
    """Ciclo generador-evaluador (`CONTEXT9.md`, checklist "Ciclo
    generador-evaluador"): si una sección falla, vuelve a invocar al
    generador de ESE departamento junto con el `feedback_for_generator`
    del `EvaluationResult` anterior -- hasta `max_iterations`. Si se agota
    el límite sin pasar, conserva el último borrador + su evaluación y
    señala `needs_human_review=True` (nunca descarta la sección).

    `generator_fn`/`evaluate_fn` son inyectables (mismo patrón de
    testabilidad que el resto del pipeline) -- ver
    `tests/pipelines/test_rfp_generation_cycle.py`, que fuerza fallos
    deterministas sin depender de que el generador real falle de verdad.
    """

    generator_fn = generator_fn or GENERATOR_REGISTRY[department_id]
    draft_content = initial_draft
    feedback: str | None = None
    evaluation_result: dict | None = None

    for iteration in range(1, max_iterations + 1):
        if iteration > 1:
            draft_content = generator_fn(key_aspects, client_country, feedback=feedback)

        evaluation_result = evaluate_fn(department_id, client_country, key_aspects, draft_content)
        if evaluation_result["overall_pass"]:
            return draft_content, evaluation_result, False

        feedback = evaluation_result["feedback_for_generator"]

    # Límite de iteraciones agotado sin pasar -- se conserva el último
    # borrador + su EvaluationResult real (nunca se descarta la sección).
    return draft_content, evaluation_result, True


def process_rfp_generation(ticket_id: int, *, session: Session | None = None) -> dict[str, Any]:
    """Consume el handoff de la Parte 1 (ticket ya en `analisis_completo`,
    con sus `RFPDepartmentSection.key_aspects` ya persistidos) y produce,
    por cada departamento activo: el borrador generado
    (`generation_graph.py`, fan-out dinámico para el intento inicial de
    todos los departamentos a la vez) y su evaluación en paralelo
    (`evaluation_graph.py`) -- con reintentos guiados por
    `feedback_for_generator` cuando una sección no pasa (ver
    `_generate_and_evaluate_with_retries`). Persiste `draft_content` +
    `evaluation_results` en la misma fila de `RFPDepartmentSection`.

    Si alguna sección agota `MAX_GENERATION_ITERATIONS` sin pasar, esa
    sección queda con `approval_status="needs_human_review"` y el ticket
    completo pasa a `TicketStatus.NEEDS_HUMAN_REVIEW` en vez de
    `EN_EVALUACION` -- nunca se descarta el ticket ni la sección.
    """

    owns_session = session is None
    active_session = session or Session(get_sql_engine())

    try:
        ticket = active_session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise ValueError(f"RFPTicket {ticket_id} no existe.")
        if ticket.status != TicketStatus.ANALISIS_COMPLETO.value:
            raise ValueError(
                f"RFPTicket {ticket_id} está en estado '{ticket.status}', se esperaba "
                f"'{TicketStatus.ANALISIS_COMPLETO.value}' (handoff de la Parte 1)."
            )

        metadata = active_session.exec(
            select(RFPMetadataRecord).where(RFPMetadataRecord.ticket_id == ticket_id)
        ).first()
        if metadata is None:
            raise ValueError(f"RFPTicket {ticket_id} no tiene RFPMetadataRecord -- handoff de Parte 1 incompleto.")

        sections = active_session.exec(
            select(RFPDepartmentSection).where(RFPDepartmentSection.ticket_id == ticket_id)
        ).all()
        sections_by_department = {section.department_id: section for section in sections}

        ticket.status = TicketStatus.GENERANDO_BORRADOR.value
        ticket.updated_at = datetime.now(timezone.utc)
        active_session.add(ticket)
        active_session.commit()

        generation_state: dict[str, Any] = {
            "client_country": metadata.client_country,
            "departments_needed": metadata.departments_needed,
        }
        for department_id, section in sections_by_department.items():
            generation_state[f"{department_id}_key_aspects"] = section.key_aspects

        generation_result = _COMPILED_GENERATION_GRAPH.invoke(generation_state)

        evaluations: dict[str, Any] = {}
        any_needs_human_review = False
        for department_id in metadata.departments_needed:
            section = sections_by_department.get(department_id)
            if section is None:
                continue

            initial_draft = generation_result.get(f"{department_id}_draft")
            if initial_draft is None:
                continue

            draft_content, evaluation_result, needs_human_review = _generate_and_evaluate_with_retries(
                department_id, metadata.client_country, section.key_aspects, initial_draft
            )

            section.draft_content = draft_content
            section.evaluation_results = evaluation_result
            section.approval_status = "needs_human_review" if needs_human_review else None
            active_session.add(section)
            evaluations[department_id] = evaluation_result
            any_needs_human_review = any_needs_human_review or needs_human_review

        ticket.status = (
            TicketStatus.NEEDS_HUMAN_REVIEW.value if any_needs_human_review else TicketStatus.EN_EVALUACION.value
        )
        ticket.updated_at = datetime.now(timezone.utc)
        active_session.add(ticket)
        active_session.commit()

        return {"ticket_id": ticket_id, "status": ticket.status, "evaluations": evaluations}
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
