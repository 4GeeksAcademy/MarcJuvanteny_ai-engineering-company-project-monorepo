"""Grafo de recepción de RFPs (`CONTEXT/CONTEXT9.md`, Hito 9 Parte 1) --
dedicado, bajo `data/pipelines/rfp_intake/`, **nunca mezclado con el grafo
CX** (`services/knowledge-api/agent_graph.py`): dos dominios de negocio
completamente distintos (comercial/RFP vs. soporte al cliente), dos
grafos separados, tal como exige la Sección 2.4 del BRIEFING.

## Patrón: orchestrator-worker-synthesizer

- `classify`: agente clasificador -- lee el Markdown, decide si es una RFP
  válida (`classifier.py::classify_rfp`) y, si lo es, extrae metadatos
  (`classifier.py::extract_metadata`) incluido `departments_needed`.
- `discarded`: terminal -- la RFP no es válida, el flujo se detiene acá
  (nunca llega a ningún worker). `CONTEXT9.md`: "no falles en silencio" --
  `discard_reason` queda en el estado y se persiste en `RFPTicket`.
- `orchestrate`: descompone en subtareas por departamento -- la
  decisión real ya la tomó `classify` (`departments_needed`); este nodo
  existe como paso explícito del patrón orchestrator-worker-synthesizer
  (deja un lugar donde, a futuro, se podría re-priorizar o re-derivar los
  departamentos sin tocar la clasificación). El fan-out a los workers
  necesarios es una arista condicional que devuelve una LISTA de nodos
  siguientes (verificado antes de construir este grafo: LangGraph soporta
  fan-out dinámico a un subconjunto de nodos vía
  `add_conditional_edges(..., routing_fn_que_devuelve_lista)` -- cada
  worker escribe a SU PROPIA clave de estado, nunca una compartida, para
  evitar el error real de LangGraph `InvalidUpdateError: Can receive only
  one value per step` que se confirmó al probar con una clave de estado
  compartida entre workers en paralelo).
- `warehouse_worker` / `lastmile_worker` / `reverse_worker`: cada uno
  llama a **una sola** función de `workers.py` -- nunca un worker que
  "hace lo que sea del departamento que toque". Solo corren los
  departamentos que `departments_needed` marcó.
- `synthesize`: consolida los `WorkerResult` de los departamentos que
  corrieron en un resumen único para Ventas (`synthesizer.py`) y deja el
  ticket listo para el handoff hacia la Parte 2.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .classifier import ClassificationResult, RFPMetadataExtraction, classify_rfp, extract_metadata
from .synthesizer import SynthesizedSummary, synthesize
from .workers import WorkerResult, run_lastmile_worker, run_reverse_worker, run_warehouse_worker

DEPARTMENT_RESULT_KEYS = {
    "warehouse": "warehouse_result",
    "lastmile": "lastmile_result",
    "reverse": "reverse_result",
}


class RFPIntakeState(TypedDict, total=False):
    markdown_text: str
    classification: dict[str, Any] | None
    metadata: dict[str, Any] | None
    warehouse_result: dict[str, Any] | None
    lastmile_result: dict[str, Any] | None
    reverse_result: dict[str, Any] | None
    summary: dict[str, Any] | None


def _make_classify_node(
    classify_fn: Callable[[str], ClassificationResult],
    extract_metadata_fn: Callable[[str], RFPMetadataExtraction],
) -> Callable[[RFPIntakeState], dict[str, Any]]:
    def classify_node(state: RFPIntakeState) -> dict[str, Any]:
        classification = classify_fn(state["markdown_text"])
        result: dict[str, Any] = {"classification": classification.model_dump()}
        if classification.is_valid:
            result["metadata"] = extract_metadata_fn(state["markdown_text"]).model_dump()
        return result

    return classify_node


def _route_after_classify(state: RFPIntakeState) -> str:
    classification = state.get("classification") or {}
    return "orchestrate" if classification.get("is_valid") else "discarded"


def _discarded_node(state: RFPIntakeState) -> dict[str, Any]:
    return {}


def _orchestrate_node(state: RFPIntakeState) -> dict[str, Any]:
    return {}


def _route_after_orchestrate(state: RFPIntakeState) -> list[str]:
    metadata = state.get("metadata") or {}
    departments_needed = metadata.get("departments_needed") or []
    return [DEPARTMENT_RESULT_KEYS[dept].removesuffix("_result") + "_worker" for dept in departments_needed]


def _make_worker_node(
    department_id: str,
    worker_fn: Callable[[RFPMetadataExtraction, str], WorkerResult],
) -> Callable[[RFPIntakeState], dict[str, Any]]:
    result_key = DEPARTMENT_RESULT_KEYS[department_id]

    def worker_node(state: RFPIntakeState) -> dict[str, Any]:
        metadata = RFPMetadataExtraction.model_validate(state["metadata"])
        result = worker_fn(metadata, state["markdown_text"])
        return {result_key: result.model_dump()}

    return worker_node


def _make_synthesize_node(
    synthesize_fn: Callable[[list[WorkerResult]], SynthesizedSummary],
) -> Callable[[RFPIntakeState], dict[str, Any]]:
    def synthesize_node(state: RFPIntakeState) -> dict[str, Any]:
        worker_results = [
            WorkerResult.model_validate(state[key])
            for key in ("warehouse_result", "lastmile_result", "reverse_result")
            if state.get(key) is not None
        ]
        summary = synthesize_fn(worker_results)
        return {"summary": summary.model_dump()}

    return synthesize_node


def build_graph(
    classify_fn: Callable[[str], ClassificationResult] = classify_rfp,
    extract_metadata_fn: Callable[[str], RFPMetadataExtraction] = extract_metadata,
    warehouse_worker_fn: Callable[[RFPMetadataExtraction, str], WorkerResult] = run_warehouse_worker,
    lastmile_worker_fn: Callable[[RFPMetadataExtraction, str], WorkerResult] = run_lastmile_worker,
    reverse_worker_fn: Callable[[RFPMetadataExtraction, str], WorkerResult] = run_reverse_worker,
    synthesize_fn: Callable[[list[WorkerResult]], SynthesizedSummary] = synthesize,
) -> CompiledStateGraph:
    """Todas las funciones de negocio son inyectables, mismo patrón que el
    grafo CX -- ver `tests/pipelines/test_rfp_classifier.py` /
    `test_rfp_workers.py` para pruebas sin PDFs reales."""

    graph = StateGraph(RFPIntakeState)

    graph.add_node("classify", _make_classify_node(classify_fn, extract_metadata_fn))
    graph.add_node("discarded", _discarded_node)
    graph.add_node("orchestrate", _orchestrate_node)
    graph.add_node("warehouse_worker", _make_worker_node("warehouse", warehouse_worker_fn))
    graph.add_node("lastmile_worker", _make_worker_node("lastmile", lastmile_worker_fn))
    graph.add_node("reverse_worker", _make_worker_node("reverse", reverse_worker_fn))
    graph.add_node("synthesize", _make_synthesize_node(synthesize_fn))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_after_classify, {"discarded": "discarded", "orchestrate": "orchestrate"})
    graph.add_conditional_edges(
        "orchestrate", _route_after_orchestrate, ["warehouse_worker", "lastmile_worker", "reverse_worker"]
    )
    graph.add_edge("warehouse_worker", "synthesize")
    graph.add_edge("lastmile_worker", "synthesize")
    graph.add_edge("reverse_worker", "synthesize")
    graph.add_edge("synthesize", END)
    graph.add_edge("discarded", END)

    return graph.compile()
