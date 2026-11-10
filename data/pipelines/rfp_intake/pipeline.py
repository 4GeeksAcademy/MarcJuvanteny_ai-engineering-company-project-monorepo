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
from functools import lru_cache
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from sqlmodel import Session, select

from .approval_graph import ApprovalDecision, build_approval_graph
from .evaluation_graph import build_evaluation_graph
from .events import record_ticket_created
from .generation_graph import build_generation_graph
from .generators import GENERATOR_REGISTRY
from .graph import build_graph
from .models import (
    FinalDocument,
    RFPDepartmentSection,
    RFPMetadataRecord,
    RFPTicket,
    TicketStatus,
    get_rfp_database_url,
    get_sql_engine,
)
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


@lru_cache(maxsize=1)
def _get_approval_checkpointer() -> PostgresSaver:
    """Conexión real a Postgres solo al PRIMER uso (`@lru_cache`), nunca
    al importar este módulo -- `pipeline.py` se importa en tests que no
    tocan la Parte 3 (p. ej. `test_rfp_generation_cycle.py`) y no deben
    requerir Postgres levantado para correr. `PostgresSaver` (no
    `MemorySaver`): checklist Parte 3, "Persiste el estado del flujo con
    un checkpointer antes de cada interrupción, para que la ejecución sea
    reanudable" -- reanudable de verdad (otro proceso, otra conexión),
    verificado antes de construir el grafo real (ver Pasos)."""

    conn = psycopg.Connection.connect(
        get_rfp_database_url(), autocommit=True, prepare_threshold=0, row_factory=dict_row
    )
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return checkpointer


@lru_cache(maxsize=1)
def _get_compiled_approval_graph():
    return build_approval_graph(checkpointer=_get_approval_checkpointer())


def _approval_thread_config(ticket_id: int) -> dict[str, Any]:
    # "Identidad del checkpointer": namespacing del thread_id por
    # ticket_id -- tickets concurrentes nunca comparten checkpoint. Un
    # solo thread por ticket (no uno por departamento): los 3
    # departamentos corren en el MISMO grafo/hilo, y el `interrupt()` de
    # LangGraph ya aísla cada rama por su propio id (verificado antes de
    # construir el grafo, ver `approval_graph.py` y Pasos) -- no hace
    # falta un hilo separado por departamento para lograrlo.
    return {"configurable": {"thread_id": f"rfp-{ticket_id}"}}


def _pending_approvals_from_interrupts(interrupts) -> list[dict[str, Any]]:
    return [{**interrupt.value, "interrupt_id": interrupt.id} for interrupt in interrupts]


def _announce_valid_rfp(
    session: Session, ticket: RFPTicket, metadata: dict[str, Any], readability_metrics: dict[str, Any]
) -> RFPMetadataRecord:
    """Persiste el `RFPMetadataRecord` + el evento `rfp_ticket_created`
    (outbox, `events.py`) en UNA transacción, con el ticket todavía en
    `analizando` -- el endpoint SSE lo emite en cuanto aparece la fila."""

    metadata_record = RFPMetadataRecord(
        ticket_id=ticket.id,
        client_name=metadata.get("client_name"),
        client_country=metadata.get("client_country"),
        services_requested=metadata.get("services_requested") or [],
        monthly_volume=metadata.get("monthly_volume"),
        deadline=metadata.get("deadline"),
        budget_range=metadata.get("budget_range"),
        departments_needed=metadata.get("departments_needed") or [],
        readability_metrics=readability_metrics,
    )
    session.add(metadata_record)
    session.flush()  # asigna metadata_record.id (= rfp_id del payload) antes de armar el evento
    record_ticket_created(session, ticket, metadata_record)
    session.commit()
    session.refresh(metadata_record)
    return metadata_record


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

        metadata_record: RFPMetadataRecord | None = None
        try:
            markdown_text = convert_pdf_to_markdown(ticket.raw_pdf_path)
            readability_metrics = compute_readability_metrics(markdown_text)
            # `stream` en vez de `invoke`: CONTEXT10.md pide notificar "en el
            # momento exacto" en que el documento queda clasificado como RFP
            # válida -- es decir, al salir del nodo `classify`, no al final
            # del grafo (workers + synthesizer tardan bastante más).
            graph_result: dict[str, Any] = {}
            for graph_result in _COMPILED_GRAPH.stream({"markdown_text": markdown_text}, stream_mode="values"):
                if metadata_record is None and (graph_result.get("classification") or {}).get("is_valid"):
                    metadata_record = _announce_valid_rfp(
                        active_session, ticket, graph_result.get("metadata") or {}, readability_metrics
                    )
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
        if metadata_record is None:
            metadata_record = _announce_valid_rfp(active_session, ticket, metadata, readability_metrics)

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


def start_or_get_approval_round(ticket_id: int, *, session: Session | None = None) -> dict[str, Any]:
    """Arranca la ronda de aprobación humana por departamento (Hito 9
    Parte 3) para un ticket que ya salió de la Parte 2
    (`en_evaluación`/`needs_human_review` -- ambos pasan a Parte 3 por
    igual, ver tabla de estados de `CONTEXT9.md` §2.3), o simplemente
    devuelve el estado actual de la ronda si ya está en curso
    (`esperando_aprobación`) o ya cerró (`terminado`) -- **nunca**
    reinvoca el grafo desde cero sobre un hilo de checkpoint que ya
    existe (`resume` es el único punto de entrada para avanzarlo, ver
    `resume_department_approval`)."""

    owns_session = session is None
    active_session = session or Session(get_sql_engine())

    try:
        ticket = active_session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise ValueError(f"RFPTicket {ticket_id} no existe.")

        compiled = _get_compiled_approval_graph()
        config = _approval_thread_config(ticket_id)

        if ticket.status == TicketStatus.TERMINADO.value:
            document = active_session.exec(
                select(FinalDocument).where(FinalDocument.ticket_id == ticket_id)
            ).first()
            return {
                "ticket_id": ticket_id,
                "status": ticket.status,
                "pending_approvals": [],
                "final_document": document.model_dump() if document else None,
            }

        if ticket.status == TicketStatus.ESPERANDO_APROBACION.value:
            state = compiled.get_state(config)
            pending_interrupts = [i for task in state.tasks for i in task.interrupts]
            return {
                "ticket_id": ticket_id,
                "status": ticket.status,
                "pending_approvals": _pending_approvals_from_interrupts(pending_interrupts),
            }

        if ticket.status not in (TicketStatus.EN_EVALUACION.value, TicketStatus.NEEDS_HUMAN_REVIEW.value):
            raise ValueError(
                f"RFPTicket {ticket_id} está en estado '{ticket.status}', se esperaba el final de la Parte 2 "
                f"('{TicketStatus.EN_EVALUACION.value}' o '{TicketStatus.NEEDS_HUMAN_REVIEW.value}')."
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

        initial_state = {
            "ticket_id": ticket_id,
            "client_country": metadata.client_country,
            "departments_needed": metadata.departments_needed,
            "sections": {
                department_id: {
                    "key_aspects": sections_by_department[department_id].key_aspects,
                    "draft_content": sections_by_department[department_id].draft_content,
                    "evaluation_results": sections_by_department[department_id].evaluation_results,
                }
                for department_id in metadata.departments_needed
                if department_id in sections_by_department
            },
            "decisions": {},
        }
        result = compiled.invoke(initial_state, config=config)

        ticket.status = TicketStatus.ESPERANDO_APROBACION.value
        ticket.updated_at = datetime.now(timezone.utc)
        active_session.add(ticket)
        active_session.commit()

        return {
            "ticket_id": ticket_id,
            "status": ticket.status,
            "pending_approvals": _pending_approvals_from_interrupts(result.get("__interrupt__", [])),
        }
    finally:
        if owns_session:
            active_session.close()


def resume_department_approval(
    ticket_id: int, department_id: str, decision: dict[str, Any], *, session: Session | None = None
) -> dict[str, Any]:
    """`resume` como punto de entrada EXPLÍCITO del grafo (checklist: "no
    como un reinicio del flujo completo") -- nunca reconstruye el estado
    inicial, solo localiza el `interrupt` pendiente de ESE departamento y
    lo reanuda con `Command(resume=...)`. La decisión humana se valida
    (`ApprovalDecision`) ANTES de construir ese `Command`, nunca después."""

    validated_decision = ApprovalDecision.model_validate(decision)

    owns_session = session is None
    active_session = session or Session(get_sql_engine())

    try:
        ticket = active_session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise ValueError(f"RFPTicket {ticket_id} no existe.")
        if ticket.status != TicketStatus.ESPERANDO_APROBACION.value:
            raise ValueError(
                f"RFPTicket {ticket_id} está en estado '{ticket.status}', se esperaba "
                f"'{TicketStatus.ESPERANDO_APROBACION.value}'."
            )

        compiled = _get_compiled_approval_graph()
        config = _approval_thread_config(ticket_id)

        state = compiled.get_state(config)
        interrupt_id = next(
            (
                i.id
                for task in state.tasks
                if task.name == f"{department_id}_approval"
                for i in task.interrupts
            ),
            None,
        )
        if interrupt_id is None:
            raise ValueError(
                f"No hay una aprobación pendiente para el departamento '{department_id}' en el ticket {ticket_id}."
            )

        result = compiled.invoke(Command(resume={interrupt_id: validated_decision.model_dump()}), config=config)

        # El reintento (rechazo con feedback) o el arbitraje pudieron
        # haber tocado MÁS de una sección, no solo `department_id` -- se
        # vuelve a persistir el snapshot completo de `sections`/`decisions`
        # que devolvió el grafo, nunca solo la rama que se reanudó.
        sections_state = result.get("sections") or {}
        decisions_state = result.get("decisions") or {}
        db_sections = active_session.exec(
            select(RFPDepartmentSection).where(RFPDepartmentSection.ticket_id == ticket_id)
        ).all()
        db_sections_by_department = {s.department_id: s for s in db_sections}
        for dept_id, section_data in sections_state.items():
            db_section = db_sections_by_department.get(dept_id)
            if db_section is None:
                continue
            decision_data = decisions_state.get(dept_id, {})
            db_section.draft_content = section_data.get("draft_content")
            db_section.evaluation_results = section_data.get("evaluation_results")
            db_section.approval_status = decision_data.get("status")
            db_section.approver = decision_data.get("approver")
            decided_at = decision_data.get("decided_at")
            db_section.approved_at = datetime.fromisoformat(decided_at) if decided_at else None
            active_session.add(db_section)

        final_document_data = result.get("final_document")
        if final_document_data:
            existing_document = active_session.exec(
                select(FinalDocument).where(FinalDocument.ticket_id == ticket_id)
            ).first()
            if existing_document is None:
                active_session.add(
                    FinalDocument(
                        ticket_id=ticket_id,
                        sections=final_document_data["sections"],
                        currency=final_document_data["currency"],
                        generated_at=datetime.fromisoformat(final_document_data["generated_at"]),
                    )
                )
            ticket.status = TicketStatus.TERMINADO.value
        else:
            # Sigue esperando (otra ronda pendiente, propia o forzada por
            # arbitraje) -- "Mientras alguna aprobación de departamento
            # esté pendiente, pon el ticket en esperando_aprobación".
            ticket.status = TicketStatus.ESPERANDO_APROBACION.value

        ticket.updated_at = datetime.now(timezone.utc)
        active_session.add(ticket)
        active_session.commit()

        return {
            "ticket_id": ticket_id,
            "status": ticket.status,
            "pending_approvals": _pending_approvals_from_interrupts(result.get("__interrupt__", [])),
            "final_document": final_document_data,
        }
    finally:
        if owns_session:
            active_session.close()


def get_ticket_with_metadata(ticket_id: int, *, session: Session | None = None) -> dict[str, Any] | None:
    """Usado por el endpoint de status (`GET /rfp/tickets/{id}`, Parte 1 --
    "la UI consulta/refresca estado") -- ticket + metadata + secciones (+
    documento final, si ya existe -- Parte 3: "déjalo accesible") ya
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
        final_document = active_session.exec(
            select(FinalDocument).where(FinalDocument.ticket_id == ticket_id)
        ).first()

        return {
            "ticket": ticket.model_dump(),
            "metadata": metadata.model_dump() if metadata else None,
            "sections": [section.model_dump() for section in sections],
            "final_document": final_document.model_dump() if final_document else None,
        }
    finally:
        if owns_session:
            active_session.close()
