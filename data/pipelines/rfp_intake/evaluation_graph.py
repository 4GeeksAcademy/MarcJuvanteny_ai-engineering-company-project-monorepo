"""Grafo de evaluación en paralelo (`CONTEXT/CONTEXT9.md`, Hito 9 Parte 2,
"Evaluación en paralelo"): "Implementa múltiples agentes evaluadores que
corran en paralelo sobre cada sección generada".

Evalúa UNA sección (de un departamento) por invocación -- `pipeline.py`
invoca este grafo una vez por sección generada. Los 3 evaluadores siempre
corren (a diferencia de `generation_graph.py`, aquí no hay fan-out
condicional por departamento: legibilidad/pertinencia/cumplimiento
siempre aplican), cada uno escribe a su propia clave de estado
(`readability_result`/`relevance_result`/`compliance_result`) -- mismo
motivo de siempre: evitar `InvalidUpdateError` por escritura concurrente a
una clave compartida. Un nodo `combine` converge después de los 3 (LangGraph
solo lo corre una vez que las 3 ramas terminaron) y arma el
`EvaluationResult` final.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .evaluators import (
    ComplianceEvaluation,
    EvaluationResult,
    ReadabilityEvaluation,
    RelevanceEvaluation,
    combine_evaluation,
    evaluate_compliance,
    evaluate_readability,
    evaluate_relevance,
)


class EvaluationState(TypedDict, total=False):
    department_id: str
    client_country: str | None
    key_aspects: dict[str, Any]
    draft_content: str
    readability_result: dict[str, Any] | None
    relevance_result: dict[str, Any] | None
    compliance_result: dict[str, Any] | None
    evaluation_result: dict[str, Any] | None


def _make_readability_node(
    evaluate_fn: Callable[[str], ReadabilityEvaluation],
) -> Callable[[EvaluationState], dict[str, Any]]:
    def readability_node(state: EvaluationState) -> dict[str, Any]:
        result = evaluate_fn(state["draft_content"])
        return {"readability_result": result.model_dump(by_alias=True)}

    return readability_node


def _make_relevance_node(
    evaluate_fn: Callable[[dict, str], RelevanceEvaluation],
) -> Callable[[EvaluationState], dict[str, Any]]:
    def relevance_node(state: EvaluationState) -> dict[str, Any]:
        result = evaluate_fn(state.get("key_aspects") or {}, state["draft_content"])
        return {"relevance_result": result.model_dump(by_alias=True)}

    return relevance_node


def _make_compliance_node(
    evaluate_fn: Callable[[str, str | None, str], ComplianceEvaluation],
) -> Callable[[EvaluationState], dict[str, Any]]:
    def compliance_node(state: EvaluationState) -> dict[str, Any]:
        result = evaluate_fn(state["department_id"], state.get("client_country"), state["draft_content"])
        return {"compliance_result": result.model_dump(by_alias=True)}

    return compliance_node


def _make_combine_node(
    combine_fn: Callable[[str, ReadabilityEvaluation, RelevanceEvaluation, ComplianceEvaluation], EvaluationResult],
) -> Callable[[EvaluationState], dict[str, Any]]:
    def combine_node(state: EvaluationState) -> dict[str, Any]:
        readability = ReadabilityEvaluation.model_validate(state["readability_result"])
        relevance = RelevanceEvaluation.model_validate(state["relevance_result"])
        compliance = ComplianceEvaluation.model_validate(state["compliance_result"])
        result = combine_fn(state["department_id"], readability, relevance, compliance)
        return {"evaluation_result": result.model_dump(by_alias=True)}

    return combine_node


def build_evaluation_graph(
    evaluate_readability_fn: Callable[[str], ReadabilityEvaluation] = evaluate_readability,
    evaluate_relevance_fn: Callable[[dict, str], RelevanceEvaluation] = evaluate_relevance,
    evaluate_compliance_fn: Callable[[str, str | None, str], ComplianceEvaluation] = evaluate_compliance,
    combine_fn: Callable[
        [str, ReadabilityEvaluation, RelevanceEvaluation, ComplianceEvaluation], EvaluationResult
    ] = combine_evaluation,
) -> CompiledStateGraph:
    """Evaluadores inyectables, mismo patrón de testabilidad que el resto
    del pipeline -- ver `tests/pipelines/test_rfp_evaluation_graph.py`."""

    graph = StateGraph(EvaluationState)

    graph.add_node("readability", _make_readability_node(evaluate_readability_fn))
    graph.add_node("relevance", _make_relevance_node(evaluate_relevance_fn))
    graph.add_node("compliance", _make_compliance_node(evaluate_compliance_fn))
    graph.add_node("combine", _make_combine_node(combine_fn))

    graph.add_edge(START, "readability")
    graph.add_edge(START, "relevance")
    graph.add_edge(START, "compliance")
    graph.add_edge("readability", "combine")
    graph.add_edge("relevance", "combine")
    graph.add_edge("compliance", "combine")
    graph.add_edge("combine", END)

    return graph.compile()
