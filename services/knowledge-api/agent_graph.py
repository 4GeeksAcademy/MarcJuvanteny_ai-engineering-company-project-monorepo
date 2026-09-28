"""Grafo del agente RAG de TrackFlow (`CONTEXT/CONTEXT7.md`, sección
"Grafo del agente" — el "proyecto posterior" que `data/pipelines/rag.py`
dejó preparado desde la Fase 2: `retrieve()` y `generate_answer()` separados
de `query()` precisamente para que un grafo como este pudiera reutilizarlos
como pasos independientes, sin ejecutar la recuperación dos veces).

## Estado del grafo

`AgentState` trae lo mínimo que un nodo necesita para decidir el siguiente
paso: la pregunta, el contexto ya recuperado (o `None` si todavía no se
recuperó), la respuesta final (o `None`), y un mensaje de error explícito
para la ruta de pregunta vacía. **Deliberadamente no incluye historial de
conversación**: cada corrida de este grafo resuelve una sola pregunta
independiente (el mismo contrato que `query()` en Fase 2) — no hay un caso
de uso todavía que justifique cargar turnos anteriores en el estado.

## Nodos y su contrato

- `receive_question`: recibe la pregunta, la normaliza (`strip()`). No llama
  a Qdrant ni al LLM.
- `retrieve`: llama a `retrieve()` de `data/pipelines/rag.py` **sin
  duplicarlo** (se importa, no se reimplementa la búsqueda vectorial).
- `generate`: llama a `generate_answer(question, context)` — **no** a
  `query()` — con el contexto que el nodo `retrieve` ya produjo. Meter
  `query()` (que vuelve a llamar a `retrieve()` internamente) en este nodo
  volvería a ejecutar la recuperación y colapsaría el grafo de vuelta a la
  secuencia monolítica que esta guía pide evitar.
- `no_context`: responde con honestidad ("no tengo información") **sin**
  llamar al modelo de generación — si `retrieve()` no encontró nada por
  encima de `min_score`, forzar una llamada al LLM sobre contexto vacío solo
  arriesgaría que invente una respuesta, que es justo lo que
  `SYSTEM_PROMPT` (Fase 2) ya intenta evitar por otro lado.
- `empty_question`: la pregunta llegó vacía — nunca se llama a `retrieve()`
  con una query vacía.

## Aristas condicionales (no una secuencia fija)

```
START -> receive_question
receive_question -> [pregunta vacía] -> empty_question -> END
                  -> [pregunta con contenido] -> retrieve
retrieve -> [sin contexto por encima de min_score] -> no_context -> END
         -> [hay contexto] -> generate -> END
```

## Checkpointing

`build_graph()` compila con un `checkpointer` (por defecto `MemorySaver`,
en memoria del proceso — no persiste entre reinicios; para eso hace falta
`SqliteSaver`/`PostgresSaver` de `langgraph-checkpoint-*`, no incluido en
esta entrega, ver `Pasos/`). Cada nodo ejecutado queda como un checkpoint
bajo el mismo `thread_id` — `compiled_graph.get_state_history(config)`
permite inspeccionar o retomar una corrida existente sin tener que
reconstruir el estado a mano.

## Trace

`run_agent()` corre el grafo con `stream_mode="updates"` (LangGraph emite
`{nodo: cambio_de_estado}` en el orden real de ejecución) y guarda esa
secuencia en `data/eval/agent-traces/<thread_id>.json` — consultable después
de la corrida (`get_trace(thread_id)`), no solo impresa en consola.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

import pipeline_path  # noqa: F401  (efecto secundario: agrega data/pipelines/ a sys.path)
from rag import generate_answer, retrieve

SERVICE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SERVICE_DIR.parent.parent
TRACE_DIR = ROOT_DIR / "data" / "eval" / "agent-traces"

NO_CONTEXT_ANSWER = "No tengo información sobre eso en la base de conocimiento de TrackFlow."
EMPTY_QUESTION_ERROR = "La pregunta no puede estar vacía."


class AgentState(TypedDict, total=False):
    question: str
    context: list[dict[str, Any]] | None
    answer: str | None
    error: str | None


def _receive_question_node(state: AgentState) -> dict[str, Any]:
    return {"question": (state.get("question") or "").strip()}


def _make_retrieve_node(retrieve_fn: Callable[[str], list[dict[str, Any]]]) -> Callable[[AgentState], dict[str, Any]]:
    def retrieve_node(state: AgentState) -> dict[str, Any]:
        return {"context": retrieve_fn(state["question"])}

    return retrieve_node


def _make_generate_node(
    generate_fn: Callable[[str, list[dict[str, Any]]], str],
) -> Callable[[AgentState], dict[str, Any]]:
    def generate_node(state: AgentState) -> dict[str, Any]:
        return {"answer": generate_fn(state["question"], state.get("context") or [])}

    return generate_node


def _no_context_node(state: AgentState) -> dict[str, Any]:
    return {"answer": NO_CONTEXT_ANSWER}


def _empty_question_node(state: AgentState) -> dict[str, Any]:
    return {"error": EMPTY_QUESTION_ERROR}


def _route_after_receive_question(state: AgentState) -> str:
    return "empty_question" if not state["question"] else "retrieve"


def _route_after_retrieve(state: AgentState) -> str:
    return "no_context" if not state.get("context") else "generate"


def build_graph(
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = generate_answer,
    checkpointer: Any = None,
) -> CompiledStateGraph:
    """Arma y compila el grafo. `retrieve_fn`/`generate_fn` inyectables para
    poder probar el enrutamiento y el contrato de nodos sin credenciales
    reales de Qdrant/4Geeks (ver `tests/pipelines/test_agent_graph.py`).

    `.compile()` valida la estructura del grafo (nodos sin conexión, aristas
    a nodos inexistentes, etc.) y lanza una excepción clara si algo está mal
    -- no se envuelve en un try/except que la esconda.
    """
    graph = StateGraph(AgentState)

    graph.add_node("receive_question", _receive_question_node)
    graph.add_node("retrieve", _make_retrieve_node(retrieve_fn))
    graph.add_node("generate", _make_generate_node(generate_fn))
    graph.add_node("no_context", _no_context_node)
    graph.add_node("empty_question", _empty_question_node)

    graph.add_edge(START, "receive_question")
    graph.add_conditional_edges(
        "receive_question",
        _route_after_receive_question,
        {"empty_question": "empty_question", "retrieve": "retrieve"},
    )
    graph.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"no_context": "no_context", "generate": "generate"},
    )
    graph.add_edge("generate", END)
    graph.add_edge("no_context", END)
    graph.add_edge("empty_question", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


def _save_trace(thread_id: str, trace: list[dict[str, Any]]) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{thread_id}.json"
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False, default=str))
    return path


def get_trace(thread_id: str) -> list[dict[str, Any]] | None:
    """Lee el trace de una corrida ya terminada. `None` si no existe."""
    path = TRACE_DIR / f"{thread_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def run_agent(
    question: str,
    *,
    thread_id: str | None = None,
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = generate_answer,
    checkpointer: Any = None,
) -> tuple[AgentState, list[dict[str, Any]], str]:
    """Corre el grafo de punta a punta. Devuelve `(estado_final, trace, thread_id)`.

    El trace es la secuencia real `[{"node": ..., "output": ...}, ...]` en
    el orden en que LangGraph ejecutó los nodos (`stream_mode="updates"`),
    guardada en disco para poder consultarla después de la corrida.
    """
    compiled_graph = build_graph(retrieve_fn=retrieve_fn, generate_fn=generate_fn, checkpointer=checkpointer)
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    trace: list[dict[str, Any]] = []
    final_state: dict[str, Any] = {"question": question}

    for update in compiled_graph.stream({"question": question}, config=config, stream_mode="updates"):
        for node_name, partial_state in update.items():
            trace.append({"node": node_name, "output": partial_state})
            final_state.update(partial_state)

    _save_trace(thread_id, trace)
    return final_state, trace, thread_id  # type: ignore[return-value]
