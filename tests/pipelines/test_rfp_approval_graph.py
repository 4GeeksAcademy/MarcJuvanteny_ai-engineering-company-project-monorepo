"""Pruebas del grafo de aprobación humana por departamento (`CONTEXT/CONTEXT9.md`,
Hito 9 Parte 3). Usa `MemorySaver` (no Postgres) para que corran rápido y
offline, con `generator_registry`/`evaluate_fn`/`trace_fn` inyectables --
mismo patrón de testabilidad del resto del pipeline.

Lo que se prueba acá NO es "¿funciona LangGraph?" (eso ya se verificó
empíricamente antes de escribir `approval_graph.py`, ver Pasos) sino que
ESTE grafo específico -- con su diseño de join estático único hacia
`arbitrate` (nunca un self-loop por departamento, ver docstring del
módulo) -- se comporta como exige el checklist: interrupción aislada por
rama, resume validado, límite de iteraciones, y cierre solo cuando TODOS
aprueban.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from rfp_intake.approval_graph import (  # noqa: E402
    ApprovalDecision,
    MAX_APPROVAL_ITERATIONS,
    build_approval_graph,
)


def _noop_trace(*args, **kwargs):
    return None


def _passing_evaluate(department_id, client_country, key_aspects, draft_content):
    return {"overall_pass": True}


def _refuse_to_be_called(*args, **kwargs):
    raise AssertionError("esta función no debería haberse llamado en este escenario")


def _build(
    *, generator_registry=None, evaluate_fn=_passing_evaluate, checkpointer=None
):
    registry = generator_registry or {
        "warehouse": lambda key_aspects, client_country, feedback=None: "borrador warehouse",
        "lastmile": lambda key_aspects, client_country, feedback=None: "borrador lastmile",
        "reverse": lambda key_aspects, client_country, feedback=None: "borrador reverse",
    }
    return build_approval_graph(
        generator_registry=registry,
        evaluate_fn=evaluate_fn,
        trace_fn=_noop_trace,
        checkpointer=checkpointer or MemorySaver(),
    )


def _initial_state(departments_needed, client_country="USA"):
    return {
        "ticket_id": 1,
        "client_country": client_country,
        "departments_needed": departments_needed,
        "sections": {
            d: {"key_aspects": {}, "draft_content": f"borrador {d} inicial", "evaluation_results": {}}
            for d in departments_needed
        },
        "decisions": {},
    }


def _interrupts_by_department(result):
    return {i.value["department_id"]: i.id for i in result["__interrupt__"]}


# --- ApprovalDecision: validación del humano ANTES de entrar al grafo ------------------


def test_approval_decision_rejects_an_invalid_decision_value():
    with pytest.raises(ValidationError):
        ApprovalDecision.model_validate({"decision": "maybe_later"})


def test_approval_decision_accepts_the_three_valid_values():
    for value in ("approve", "reject", "request_changes"):
        ApprovalDecision.model_validate({"decision": value})


# --- Aislamiento por rama: resolver un departamento no afecta al otro -------------------


def test_resolving_one_department_does_not_affect_the_other_pending_one():
    compiled = _build()
    config = {"configurable": {"thread_id": "t-1"}}

    result = compiled.invoke(_initial_state(["warehouse", "lastmile"]), config=config)
    interrupts = _interrupts_by_department(result)
    assert set(interrupts) == {"warehouse", "lastmile"}

    result2 = compiled.invoke(Command(resume={interrupts["warehouse"]: {"decision": "approve"}}), config=config)

    assert result2["decisions"]["warehouse"]["status"] == "approved"
    assert "__interrupt__" in result2
    assert [i.value["department_id"] for i in result2["__interrupt__"]] == ["lastmile"]


# --- Rechazo con feedback -> regenera -> re-interrumpe para el MISMO departamento -------


def test_reject_regenerates_with_feedback_and_reinterrupts_only_that_department():
    calls = []

    def warehouse_generator(key_aspects, client_country, feedback=None):
        calls.append(feedback)
        return f"borrador warehouse v{len(calls) + 1}"

    compiled = _build(
        generator_registry={
            "warehouse": warehouse_generator,
            "lastmile": _refuse_to_be_called,
            "reverse": _refuse_to_be_called,
        }
    )
    config = {"configurable": {"thread_id": "t-2"}}

    result = compiled.invoke(_initial_state(["warehouse"]), config=config)
    wh_id = result["__interrupt__"][0].id

    result2 = compiled.invoke(
        Command(resume={wh_id: {"decision": "reject", "reason": "falta el volumen"}}), config=config
    )

    assert result2["decisions"]["warehouse"]["status"] == "pending"
    assert result2["sections"]["warehouse"]["draft_content"] == "borrador warehouse v2"
    assert calls == ["falta el volumen"]
    assert "__interrupt__" in result2


def test_exhausting_iterations_without_approval_settles_as_rejected_final():
    def always_rejecting_generator(key_aspects, client_country, feedback=None):
        return "borrador sin cambios"

    compiled = _build(generator_registry={
        "warehouse": always_rejecting_generator,
        "lastmile": _refuse_to_be_called,
        "reverse": _refuse_to_be_called,
    })
    config = {"configurable": {"thread_id": "t-3"}}

    result = compiled.invoke(_initial_state(["warehouse"]), config=config)
    for _ in range(MAX_APPROVAL_ITERATIONS + 2):
        if "__interrupt__" not in result:
            break
        interrupt_id = result["__interrupt__"][0].id
        result = compiled.invoke(Command(resume={interrupt_id: {"decision": "reject", "reason": "no"}}), config=config)

    assert "__interrupt__" not in result
    assert result["decisions"]["warehouse"]["status"] == "rejected_final"
    assert result["decisions"]["warehouse"]["iterations"] >= MAX_APPROVAL_ITERATIONS
    # Nunca se descarta la sección -- el último borrador real queda.
    assert result["sections"]["warehouse"]["draft_content"] == "borrador sin cambios"


# --- Cierre del documento: solo cuando TODOS aprueban -----------------------------------


def test_final_document_is_only_built_when_every_department_approves():
    compiled = _build(generator_registry={
        "warehouse": lambda *a, **k: "borrador warehouse",
        "lastmile": lambda *a, **k: "no cambia",
        "reverse": _refuse_to_be_called,
    })
    config = {"configurable": {"thread_id": "t-4"}}

    result = compiled.invoke(_initial_state(["warehouse", "lastmile"]), config=config)
    interrupts = _interrupts_by_department(result)

    result2 = compiled.invoke(
        Command(resume={
            interrupts["warehouse"]: {"decision": "approve"},
            interrupts["lastmile"]: {"decision": "reject", "reason": "no me convence"},
        }),
        config=config,
    )
    # lastmile sigue pendiente (reintento) -- nunca se cierra con una aprobación faltante.
    assert result2.get("final_document") is None

    lm_id = result2["__interrupt__"][0].id
    result3 = compiled.invoke(Command(resume={lm_id: {"decision": "approve"}}), config=config)

    assert result3["final_document"] is not None
    # warehouse se aprobó en el primer intento -- nunca llamó a su
    # generador, el documento final conserva el borrador inicial tal cual.
    assert result3["final_document"]["sections"]["warehouse"] == "borrador warehouse inicial"
    assert result3["final_document"]["currency"] == "USD"
    assert "__interrupt__" not in result3


def test_ticket_level_caller_never_sees_a_final_document_if_a_department_is_rejected_final():
    def always_rejecting(key_aspects, client_country, feedback=None):
        return "sin cambios"

    compiled = _build(generator_registry={
        "warehouse": always_rejecting,
        "lastmile": _refuse_to_be_called,
        "reverse": _refuse_to_be_called,
    })
    config = {"configurable": {"thread_id": "t-5"}}

    result = compiled.invoke(_initial_state(["warehouse"]), config=config)
    for _ in range(MAX_APPROVAL_ITERATIONS + 2):
        if "__interrupt__" not in result:
            break
        interrupt_id = result["__interrupt__"][0].id
        result = compiled.invoke(Command(resume={interrupt_id: {"decision": "reject"}}), config=config)

    assert result["decisions"]["warehouse"]["status"] == "rejected_final"
    assert result.get("final_document") is None


# --- Arbitraje: fuerza una reescritura y reabre la aprobación ---------------------------


def test_arbitration_reopens_an_already_approved_department_when_a_trigger_fires():
    """Un currency-mismatch real: el humano aprueba un borrador con la
    moneda incorrecta -- `arbitrate` lo detecta, lo reescribe, y vuelve a
    pedir aprobación -- nunca deja pasar un conflicto real solo porque un
    humano ya dijo que sí."""

    def evaluate_fn(department_id, client_country, key_aspects, draft_content):
        return {"overall_pass": True}

    compiled = _build(
        generator_registry={
            "warehouse": lambda key_aspects, client_country, feedback=None: "Costo cotizado en USD (corregido).",
            "lastmile": _refuse_to_be_called,
            "reverse": _refuse_to_be_called,
        },
        evaluate_fn=evaluate_fn,
    )
    config = {"configurable": {"thread_id": "t-6"}}

    state = _initial_state(["warehouse"], client_country="USA")
    state["sections"]["warehouse"]["draft_content"] = "Costo cotizado en EUR por error."
    result = compiled.invoke(state, config=config)
    wh_id = result["__interrupt__"][0].id

    result2 = compiled.invoke(Command(resume={wh_id: {"decision": "approve"}}), config=config)

    assert "__interrupt__" in result2, "arbitrate debió forzar una nueva ronda, no cerrar directo"
    assert result2["decisions"]["warehouse"]["status"] == "pending"
    assert result2["decisions"]["warehouse"]["arbitration_trigger"] == "currency-mismatch"
    assert result2["sections"]["warehouse"]["draft_content"] == "Costo cotizado en USD (corregido)."
    assert len(result2["arbitration_log"]) == 1

    wh_id2 = result2["__interrupt__"][0].id
    result3 = compiled.invoke(Command(resume={wh_id2: {"decision": "approve"}}), config=config)
    assert result3["final_document"] is not None


def test_clean_proposal_never_triggers_arbitration():
    compiled = _build()
    config = {"configurable": {"thread_id": "t-7"}}

    result = compiled.invoke(_initial_state(["warehouse"]), config=config)
    wh_id = result["__interrupt__"][0].id
    result2 = compiled.invoke(Command(resume={wh_id: {"decision": "approve"}}), config=config)

    assert result2.get("arbitration_log") in (None, [])
    assert result2["final_document"] is not None
