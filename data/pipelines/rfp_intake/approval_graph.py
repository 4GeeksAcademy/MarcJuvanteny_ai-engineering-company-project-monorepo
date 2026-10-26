"""Grafo de aprobación humana por departamento (`CONTEXT/CONTEXT9.md`,
Hito 9 Parte 3): "el responsable nombrado de cada departamento activo
(§2.1) aprueba su sección de forma independiente, sin bloquear a los
demás, y el documento final se genera solo cuando todas las secciones
activas están aprobadas."

## Por qué un único grafo con `interrupt`/`Command(resume=...)`, no 3 grafos

Verificado empíricamente antes de escribir este módulo (no asumido):
cuando dos nodos en paralelo llaman `interrupt()` dentro del MISMO
`thread_id`, LangGraph genera un `Interrupt` independiente por nodo
(`id` propio); resolver uno con `Command(resume={ese_id: valor})` avanza
SOLO esa rama -- la otra queda pausada, intacta, resumible después
(incluso desde una conexión de Postgres completamente nueva, en otro
proceso). Eso es exactamente "la interrupción debe pausar únicamente la
rama... sin bloquear el avance de los departamentos que sí [decidieron]"
-- un solo grafo por ticket ya lo da gratis, sin necesitar un
`thread_id` separado por departamento.

## Por qué NINGÚN nodo de departamento se auto-enlaza (sin self-loop)

Primer diseño probado (y descartado -- ver `Pasos/`): que
`{dept}_approval` decidiera por sí mismo "vuelvo a interrumpirme" vs "voy
a `arbitrate`" producía una condición de carrera real, reproducida
corriendo el grafo antes de aceptar el diseño: si warehouse se aprueba y
lastmile necesita otra ronda en el MISMO superstep, warehouse enruta a
`arbitrate` mientras lastmile se auto-enlaza -- `arbitrate` corre
JUSTO AHÍ (su único predecesor activo ese superstep ya terminó), sin
"saber" que lastmile todavía tiene una ronda pendiente, y la condición
condicional de `arbitrate` también intenta enrutar de vuelta a
`lastmile_approval` -- dos caminos distintos agendando el mismo nodo en
el mismo superstep, duplicando la interrupción.

Corrección real: CADA resultado de `{dept}_approval` (aprobado, rechazo
con reintentos restantes, o rechazo agotado) toma la MISMA arista
estática hacia `arbitrate` -- igual que `warehouse_worker`/`lastmile_worker`
→ `synthesize` en `graph.py` (Parte 1), un join verdadero que SÍ espera a
todos los departamentos activos de la ronda porque ninguno se desvía por
su cuenta. `arbitrate` es el ÚNICO lugar que decide si hace falta otra
ronda (por un rechazo normal que todavía tiene reintentos, o por un
trigger de conflicto cruzado) y reenruta con la MISMA función que usa
`START` (`_route_to_approval_or_close`) -- un único límite de iteraciones
compartido (`MAX_APPROVAL_ITERATIONS` por departamento,
`MAX_ARBITRATION_ROUNDS` para el arbitraje) gobierna cuántas rondas
puede dar el grafo antes de cerrar.

## Trazabilidad

Cada nodo llama a `trace_fn` (inyectable, default `_default_trace`
escribe en `RFPNodeTrace`/Postgres) con agente, input, output y
timestamp -- CONTEXT9.md Parte 3, "Guardrails y control de flujo".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Callable, Literal, TypedDict
import operator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from .arbitration import WAREHOUSE_MAX_MONTHLY_CAPACITY, ArbitrationDecision, run_arbitration
from .departments import DEPARTMENTS
from .evaluators import combine_evaluation, evaluate_compliance, evaluate_readability, evaluate_relevance
from .generators import CURRENCY_BY_COUNTRY, DEFAULT_CURRENCY, GENERATOR_REGISTRY

# CONTEXT9.md §3, "Métricas de negocio": "Tiempo de aprobación por
# departamento" -- igual que Parte 2, un tope de 3 (decisión inicial + 2
# reintentos con feedback) evita un ciclo rechazo-regeneración indefinido
# sin ser tan bajo que un aprobador no pueda pedir dos rondas de cambios
# reales.
MAX_APPROVAL_ITERATIONS = 3

# "Define un límite máximo de iteraciones en cualquier ciclo restante
# entre departamentos" -- el arbitraje puede forzar como mucho 2 rondas
# de reescritura antes de dejar el conflicto sin resolver (consistente
# con la regla explícita de `currency-mismatch`: "rechazar si no se
# resuelve tras el límite de iteraciones").
MAX_ARBITRATION_ROUNDS = 2


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject", "request_changes"]
    reason: str | None = None


class ApprovalState(TypedDict, total=False):
    ticket_id: int
    client_country: str | None
    departments_needed: list[str]
    sections: Annotated[dict[str, dict[str, Any]], operator.or_]
    decisions: Annotated[dict[str, dict[str, Any]], operator.or_]
    arbitration_log: Annotated[list[dict[str, Any]], operator.add]
    arbitration_rounds: int
    final_document: dict[str, Any] | None


def _default_evaluate(department_id: str, client_country: str | None, key_aspects: dict, draft_content: str) -> dict:
    readability = evaluate_readability(draft_content)
    relevance = evaluate_relevance(key_aspects, draft_content)
    compliance = evaluate_compliance(department_id, client_country, draft_content)
    return combine_evaluation(department_id, readability, relevance, compliance).model_dump(by_alias=True)


def _default_trace(
    ticket_id: int,
    department_id: str | None,
    node_name: str,
    agent: str,
    input_: dict[str, Any],
    output: dict[str, Any] | None,
) -> None:
    from sqlmodel import Session

    from .models import RFPNodeTrace, get_sql_engine

    with Session(get_sql_engine()) as session:
        session.add(
            RFPNodeTrace(
                ticket_id=ticket_id,
                department_id=department_id,
                node_name=node_name,
                agent=agent,
                input=input_,
                output=output,
            )
        )
        session.commit()


def _needs_decision(decisions: dict[str, dict[str, Any]], department_id: str) -> bool:
    return decisions.get(department_id, {}).get("status") not in ("approved", "rejected_final")


def _route_to_approval_or_close(state: ApprovalState) -> list[str]:
    departments_needed = state.get("departments_needed") or []
    decisions = state.get("decisions") or {}
    pending = [d for d in departments_needed if _needs_decision(decisions, d)]
    if pending:
        return [f"{d}_approval" for d in pending]
    return ["close_document"]


def _make_approval_node(
    department_id: str,
    generator_fn: Callable[..., str],
    evaluate_fn: Callable[[str, str | None, dict, str], dict],
    trace_fn: Callable[..., None],
) -> Callable[[ApprovalState], dict[str, Any]]:
    approver = DEPARTMENTS[department_id].responsible

    def node(state: ApprovalState) -> dict[str, Any]:
        ticket_id = state["ticket_id"]
        client_country = state.get("client_country")
        section = state["sections"][department_id]
        prior = (state.get("decisions") or {}).get(department_id, {})
        iterations = prior.get("iterations", 0)

        request_payload = {
            "ticket_id": ticket_id,
            "department_id": department_id,
            "approver": approver,
            "draft_content": section["draft_content"],
            "evaluation_results": section.get("evaluation_results"),
            "iteration": iterations,
        }
        trace_fn(ticket_id, department_id, f"{department_id}_approval", approver, request_payload, None)

        raw_response = interrupt(request_payload)
        # "Valida la respuesta humana al reanudar... antes de dejarla
        # entrar de nuevo al grafo" -- nunca se confía en el payload crudo.
        decision = ApprovalDecision.model_validate(raw_response)

        trace_fn(
            ticket_id, department_id, f"{department_id}_approval", approver, {"raw_response": raw_response},
            decision.model_dump(),
        )

        now = datetime.now(timezone.utc).isoformat()

        if decision.decision == "approve":
            return {
                "decisions": {
                    department_id: {
                        "status": "approved",
                        "approver": approver,
                        "reason": decision.reason,
                        "iterations": iterations,
                        "decided_at": now,
                    }
                }
            }

        if iterations >= MAX_APPROVAL_ITERATIONS:
            return {
                "decisions": {
                    department_id: {
                        "status": "rejected_final",
                        "approver": approver,
                        "reason": decision.reason,
                        "iterations": iterations,
                        "decided_at": now,
                    }
                }
            }

        new_draft = generator_fn(section["key_aspects"], client_country, feedback=decision.reason)
        new_evaluation = evaluate_fn(department_id, client_country, section["key_aspects"], new_draft)
        trace_fn(
            ticket_id, department_id, f"{department_id}_regeneration", "system", {"reason": decision.reason},
            {"draft_content": new_draft},
        )

        return {
            "sections": {
                department_id: {**section, "draft_content": new_draft, "evaluation_results": new_evaluation}
            },
            "decisions": {department_id: {"status": "pending", "iterations": iterations + 1}},
        }

    return node


def _apply_arbitration_fix(decision: ArbitrationDecision, key_aspects: dict[str, Any]) -> dict[str, Any]:
    """`decision.rule_applied` (texto) ya sirve como `feedback` para que
    `generators.py::_apply_feedback` reaccione a los triggers que
    reconoce por token (`currency-mismatch`, `returns-sla-breach` --
    verificado con un caso real: una sección con moneda incorrecta se
    reescribe limpia tras pasar por `arbitrate`). `volume-vs-capacity` es
    distinto: la regla exige CAMBIAR un número real (`monthly_volume`),
    no agregar una aclaración de texto -- sin esto, el borrador
    regenerado repetiría el mismo volumen y el trigger volvería a
    disparar indefinidamente (encontrado corriendo este caso real contra
    el ticket 2 de la Parte 1, ver Pasos)."""

    if decision.trigger_id == "volume-vs-capacity" and key_aspects.get("monthly_volume") is not None:
        return {**key_aspects, "monthly_volume": WAREHOUSE_MAX_MONTHLY_CAPACITY}
    return key_aspects


def _make_arbitrate_node(
    generator_registry: dict[str, Callable[..., str]],
    evaluate_fn: Callable[[str, str | None, dict, str], dict],
    trace_fn: Callable[..., None],
) -> Callable[[ApprovalState], dict[str, Any]]:
    def node(state: ApprovalState) -> dict[str, Any]:
        ticket_id = state["ticket_id"]
        client_country = state.get("client_country")
        sections = state.get("sections") or {}
        decisions = state.get("decisions") or {}
        rounds = state.get("arbitration_rounds", 0)

        if rounds >= MAX_ARBITRATION_ROUNDS:
            trace_fn(ticket_id, None, "arbitrate", "system", {"rounds": rounds}, {"skipped": "límite de rondas de arbitraje agotado"})
            return {}

        triggered = run_arbitration(sections, client_country)
        trace_fn(
            ticket_id, None, "arbitrate", "system",
            {"decisions": decisions},
            {"triggers": [d.trigger_id for d in triggered]},
        )
        if not triggered:
            return {}

        updated_sections: dict[str, dict[str, Any]] = {}
        updated_decisions: dict[str, dict[str, Any]] = {}
        for decision in triggered:
            for department_id in decision.affected_departments:
                section = sections.get(department_id)
                if section is None:
                    continue
                generator_fn = generator_registry[department_id]
                fixed_key_aspects = _apply_arbitration_fix(decision, section["key_aspects"])
                new_draft = generator_fn(fixed_key_aspects, client_country, feedback=decision.rule_applied)
                new_evaluation = evaluate_fn(department_id, client_country, fixed_key_aspects, new_draft)
                updated_sections[department_id] = {
                    **section,
                    "key_aspects": fixed_key_aspects,
                    "draft_content": new_draft,
                    "evaluation_results": new_evaluation,
                }
                updated_decisions[department_id] = {
                    "status": "pending",
                    "iterations": 0,
                    "arbitration_trigger": decision.trigger_id,
                    "arbiter": decision.arbiter,
                }

        return {
            "sections": updated_sections,
            "decisions": updated_decisions,
            "arbitration_log": [d.model_dump() for d in triggered],
            "arbitration_rounds": rounds + 1,
        }

    return node


def _make_close_document_node(trace_fn: Callable[..., None]) -> Callable[[ApprovalState], dict[str, Any]]:
    def node(state: ApprovalState) -> dict[str, Any]:
        ticket_id = state["ticket_id"]
        client_country = state.get("client_country")
        departments_needed = state.get("departments_needed") or []
        decisions = state.get("decisions") or {}
        sections = state.get("sections") or {}

        all_approved = all(decisions.get(d, {}).get("status") == "approved" for d in departments_needed)
        trace_fn(ticket_id, None, "close_document", "system", {"decisions": decisions}, {"all_approved": all_approved})

        if not all_approved:
            return {"final_document": None}

        currency = CURRENCY_BY_COUNTRY.get(client_country or "", DEFAULT_CURRENCY)
        document = {
            "ticket_id": ticket_id,
            "sections": {d: sections[d]["draft_content"] for d in departments_needed},
            "currency": currency,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"final_document": document}

    return node


def build_approval_graph(
    *,
    generator_registry: dict[str, Callable[..., str]] = GENERATOR_REGISTRY,
    evaluate_fn: Callable[[str, str | None, dict, str], dict] = _default_evaluate,
    trace_fn: Callable[..., None] = _default_trace,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """`generator_registry`/`evaluate_fn`/`trace_fn` inyectables -- mismo
    patrón de testabilidad del resto del pipeline (ver
    `tests/pipelines/test_rfp_approval_graph.py`, que usa `MemorySaver` y
    fakes deterministas en vez de Postgres real)."""

    graph = StateGraph(ApprovalState)

    for department_id in DEPARTMENTS:
        generator_fn = generator_registry[department_id]
        graph.add_node(
            f"{department_id}_approval", _make_approval_node(department_id, generator_fn, evaluate_fn, trace_fn)
        )
        # Arista ESTÁTICA, nunca condicional -- ver docstring del módulo
        # ("Por qué ningún nodo de departamento se auto-enlaza"): todo
        # resultado de este nodo converge en el mismo join real.
        graph.add_edge(f"{department_id}_approval", "arbitrate")

    graph.add_node("arbitrate", _make_arbitrate_node(generator_registry, evaluate_fn, trace_fn))
    graph.add_node("close_document", _make_close_document_node(trace_fn))

    approval_targets = {f"{d}_approval": f"{d}_approval" for d in DEPARTMENTS}
    approval_targets["close_document"] = "close_document"

    graph.add_conditional_edges(START, _route_to_approval_or_close, approval_targets)
    graph.add_conditional_edges("arbitrate", _route_to_approval_or_close, approval_targets)
    graph.add_edge("close_document", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())
