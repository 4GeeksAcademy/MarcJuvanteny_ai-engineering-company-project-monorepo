"""Grafo de generación por departamento (`CONTEXT/CONTEXT9.md`, Hito 9
Parte 2, "Generación por departamento"): "Implementa un agente generador
por departamento que reciba el resumen relevante producido en la Parte 1".

Mismo patrón de fan-out dinámico que `graph.py` (Parte 1): una arista
condicional que devuelve una LISTA de nodos siguientes, uno por
departamento activo (`departments_needed`), cada uno escribiendo a su
propia clave de estado (`{dept}_draft`) -- nunca una clave compartida,
mismo motivo ya verificado en Parte 1 (`InvalidUpdateError` de LangGraph
con escrituras concurrentes a una clave compartida).

No hay nodo "orchestrate" ni "synthesize" acá -- a diferencia de Parte 1,
la Parte 2 no combina los borradores en un resumen único; cada
`{dept}_draft` se persiste por separado en su propia fila de
`RFPDepartmentSection` (`pipeline.py`).
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .generators import (
    GENERATOR_REGISTRY,
    generate_lastmile_section,
    generate_reverse_section,
    generate_warehouse_section,
)

DEPARTMENT_DRAFT_KEYS = {
    "warehouse": "warehouse_draft",
    "lastmile": "lastmile_draft",
    "reverse": "reverse_draft",
}


class GenerationState(TypedDict, total=False):
    client_country: str | None
    departments_needed: list[str]
    warehouse_key_aspects: dict[str, Any] | None
    lastmile_key_aspects: dict[str, Any] | None
    reverse_key_aspects: dict[str, Any] | None
    warehouse_draft: str | None
    lastmile_draft: str | None
    reverse_draft: str | None


def _route_to_generators(state: GenerationState) -> list[str]:
    departments_needed = state.get("departments_needed") or []
    return [f"{dept}_generator" for dept in departments_needed]


def _make_generator_node(
    department_id: str,
    generator_fn: Callable[[dict, str | None], str],
) -> Callable[[GenerationState], dict[str, Any]]:
    draft_key = DEPARTMENT_DRAFT_KEYS[department_id]
    key_aspects_key = f"{department_id}_key_aspects"

    def generator_node(state: GenerationState) -> dict[str, Any]:
        key_aspects = state.get(key_aspects_key) or {}
        draft = generator_fn(key_aspects, state.get("client_country"))
        return {draft_key: draft}

    return generator_node


def build_generation_graph(
    warehouse_generator_fn: Callable[[dict, str | None], str] = generate_warehouse_section,
    lastmile_generator_fn: Callable[[dict, str | None], str] = generate_lastmile_section,
    reverse_generator_fn: Callable[[dict, str | None], str] = generate_reverse_section,
) -> CompiledStateGraph:
    """Generadores inyectables, mismo patrón de testabilidad que
    `graph.py::build_graph` -- ver `tests/pipelines/test_rfp_generation_graph.py`."""

    graph = StateGraph(GenerationState)

    graph.add_node("warehouse_generator", _make_generator_node("warehouse", warehouse_generator_fn))
    graph.add_node("lastmile_generator", _make_generator_node("lastmile", lastmile_generator_fn))
    graph.add_node("reverse_generator", _make_generator_node("reverse", reverse_generator_fn))

    graph.add_conditional_edges(
        START, _route_to_generators, ["warehouse_generator", "lastmile_generator", "reverse_generator"]
    )
    graph.add_edge("warehouse_generator", END)
    graph.add_edge("lastmile_generator", END)
    graph.add_edge("reverse_generator", END)

    return graph.compile()


assert set(DEPARTMENT_DRAFT_KEYS) == set(GENERATOR_REGISTRY)
