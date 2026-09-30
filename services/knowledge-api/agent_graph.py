"""Grafo del agente RAG de TrackFlow (`CONTEXT/CONTEXT7.md`, secciones
"Grafo del agente" + "Tool obligatoria" + "Enrutamiento del agente" — el
"proyecto posterior" que `data/pipelines/rag.py` dejó preparado desde la
Fase 2: `retrieve()` y `generate_answer()` separados de `query()`
precisamente para que un grafo como este pudiera reutilizarlos como pasos
independientes, sin ejecutar la recuperación dos veces).

## Migración a MCP (checklist "Migración del agente")

Los nodos `incidents_tool`/`inventory_tool` ya NO llaman directamente a
`services/incidents-api` por HTTP -- pasan por `mcps/trackflow-mcp` (el MCP
Server) vía `langchain-mcp-adapters` (`mcp_client.py::call_mcp_tool`). La
implementación HTTP directa anterior (`tools/incidents_tool.py`,
`tools/inventory_tool.py`) se **eliminó** (no se dejó deprecada-pero-viva):
el agente tiene un único camino posible hacia el Incidents Manager, nunca
dos. El contrato de estos dos nodos no cambió (siguen devolviendo
`{"ok": ..., "incidents"|"products": [...], "error": ...}` en
`tool_result`), así que el resto del grafo (enrutamiento, `tool_failed`,
`_tool_result_to_context_chunks`) no se tocó.

Como las llamadas MCP son async (`langchain_mcp_adapters`), `incidents_tool`
e `inventory_tool` ahora son nodos `async def` -- LangGraph soporta nodos
sync y async mezclados en el mismo grafo bajo `.astream()`/`.ainvoke()`
(verificado con un grafo mínimo de prueba antes de migrar, no asumido).
`run_agent()` pasó de `compiled_graph.stream(...)` a
`await compiled_graph.astream(...)`, y `routers/agent.py::query_agent` pasó
a `async def` -- FastAPI soporta handlers async nativamente, cambio
mínimo.

## Estado del grafo

`AgentState` trae lo mínimo que un nodo necesita para decidir el siguiente
paso: la pregunta, la ruta elegida (`route`), el contexto RAG ya recuperado,
el resultado crudo de una tool (o `None`), la respuesta final, y un mensaje
de error para la ruta de pregunta vacía. **Deliberadamente no incluye
historial de conversación**: cada corrida resuelve una sola pregunta
independiente — no hay un caso de uso todavía que justifique cargar turnos
anteriores en el estado.

## Nodos y su contrato

- `receive_question`: recibe la pregunta, la normaliza (`strip()`).
- `classify_intent`: decide `route` (`"rag"` | `"incidents_tool"` |
  `"inventory_tool"` | `"both"`) a partir de la pregunta — ver
  `classify_intent()` más abajo.
- `retrieve`: llama a `retrieve()` de `data/pipelines/rag.py` **sin
  duplicarlo**.
- `incidents_tool` / `inventory_tool`: cada una llama a **una sola** tool de
  `tools/` — nunca una tool que "busca tickets o inventario según el caso".
  Ambas son de solo lectura (`GET`), con timeout explícito
  (`tools/backend_client.py::DEFAULT_TIMEOUT_SECONDS`) y devuelven un
  resultado tipado con `ok: bool` — nunca lanzan la excepción cruda del
  HTTP hacia el grafo.
- `tool_failed`: la tool agotó el timeout, falló, o el ticket/SKU no existe
  — responde con honestidad ("no pude confirmar...") **sin** llamar al
  modelo de generación, para que un fallo de red nunca se disfrace de un
  estado inventado.
- `generate`: llama a `generate_answer(question, context)` — **no** a
  `query()` — con el contexto RAG **y/o** el resultado de una tool exitosa
  (convertido a chunks de contexto por `_tool_result_to_context_chunks()`,
  mismo formato que un chunk de Qdrant, para no tener que cambiar la firma
  de `generate_answer()`). Meter `query()` en este nodo volvería a ejecutar
  la recuperación y colapsaría el grafo a la secuencia monolítica que la
  guía pide evitar.
- `no_context`: responde con honestidad, sin llamar al LLM, cuando ni el RAG
  ni una tool trajeron nada.
- `empty_question`: la pregunta llegó vacía — nunca se llama a `retrieve()`
  ni a una tool con una query vacía.

## Enrutamiento (`classify_intent`)

Heurística determinista por palabras clave — un stand-in documentado de lo
que idealmente sería una clasificación por LLM (`GENERATION_MODEL`): sin
credenciales reales de 4Geeks en este repo no se puede probar esa versión de
forma confiable y offline, así que se implementa con un método 100%
verificable en tests. El punto de inyección (`classify_fn` en
`build_graph()`) ya deja lista la sustitución por un router basado en LLM el
día que haya credenciales.

## Aristas condicionales (no una secuencia fija)

```
START -> receive_question
receive_question -> [vacía] -> empty_question -> END
                  -> [con contenido] -> classify_intent

classify_intent -> [route="rag"]             -> retrieve
                 -> [route="incidents_tool"] -> incidents_tool
                 -> [route="inventory_tool"] -> inventory_tool
                 -> [route="both"]           -> incidents_tool (y luego retrieve)

incidents_tool -> [route="both"]          -> retrieve
               -> [tool ok]               -> generate
               -> [tool falló]            -> tool_failed -> END

inventory_tool -> [tool ok] -> generate
               -> [tool falló] -> tool_failed -> END

retrieve -> [sin contexto RAG Y sin tool ok] -> no_context -> END
         -> [hay contexto RAG o tool ok]     -> generate -> END
```

## Checkpointing

`build_graph()` compila con un `checkpointer` (por defecto `MemorySaver`,
en memoria del proceso — no persiste entre reinicios; para eso hace falta
`SqliteSaver`/`PostgresSaver` de `langgraph-checkpoint-*`, no incluido en
esta entrega, ver `Pasos/`). Cada nodo ejecutado queda como un checkpoint
bajo el mismo `thread_id` — `compiled_graph.get_state_history(config)`
permite inspeccionar o retomar una corrida existente.

## Trace

`run_agent()` corre el grafo con `stream_mode="updates"` (LangGraph emite
`{nodo: cambio_de_estado}` en el orden real de ejecución) y guarda esa
secuencia en `data/eval/agent-traces/<thread_id>.json` — consultable después
de la corrida (`get_trace(thread_id)`). El orden de nodos en el trace
muestra con claridad si se usó el RAG (`retrieve`), una tool
(`incidents_tool`/`inventory_tool`), o ambos, y en qué orden.
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
from intent_extraction import extract_incident_query, extract_inventory_query
from mcp_client import call_mcp_tool

SERVICE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SERVICE_DIR.parent.parent
TRACE_DIR = ROOT_DIR / "data" / "eval" / "agent-traces"

NO_CONTEXT_ANSWER = "No tengo información sobre eso en la base de conocimiento de TrackFlow."
EMPTY_QUESTION_ERROR = "La pregunta no puede estar vacía."

_INCIDENT_KEYWORDS = ("ticket", "tickets", "incidencia", "incidencias", "incident")
_INVENTORY_KEYWORDS = ("stock", "inventario", "unidades disponibles", "existencias")
_POLICY_KEYWORDS = ("política", "politica", "sla", "devolución", "devolucion", "cobertura", "tarifa", "descuento")


class AgentState(TypedDict, total=False):
    question: str
    route: str | None
    context: list[dict[str, Any]] | None
    tool_result: dict[str, Any] | None
    answer: str | None
    error: str | None


def classify_intent(question: str) -> str:
    """`"rag"` | `"incidents_tool"` | `"inventory_tool"` | `"both"` — ver
    "Enrutamiento" en el docstring del módulo."""
    lowered = question.lower()
    wants_incidents = any(keyword in lowered for keyword in _INCIDENT_KEYWORDS)
    wants_inventory = any(keyword in lowered for keyword in _INVENTORY_KEYWORDS)

    if wants_incidents:
        if any(keyword in lowered for keyword in _POLICY_KEYWORDS):
            return "both"
        return "incidents_tool"
    if wants_inventory:
        return "inventory_tool"
    return "rag"


def _receive_question_node(state: AgentState) -> dict[str, Any]:
    return {"question": (state.get("question") or "").strip()}


def _make_classify_node(classify_fn: Callable[[str], str]) -> Callable[[AgentState], dict[str, Any]]:
    def classify_node(state: AgentState) -> dict[str, Any]:
        return {"route": classify_fn(state["question"])}

    return classify_node


def _make_retrieve_node(retrieve_fn: Callable[[str], list[dict[str, Any]]]) -> Callable[[AgentState], dict[str, Any]]:
    def retrieve_node(state: AgentState) -> dict[str, Any]:
        return {"context": retrieve_fn(state["question"])}

    return retrieve_node


async def _default_incidents_tool_call(args: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("query_incident_tool", args)


async def _default_inventory_tool_call(args: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("query_inventory_tool", args)


def _make_incidents_tool_node(
    incidents_tool_fn: Callable[[dict[str, Any]], Any],
) -> Callable[[AgentState], Any]:
    async def incidents_tool_node(state: AgentState) -> dict[str, Any]:
        query = extract_incident_query(state["question"])
        result = await incidents_tool_fn({"query": query})
        return {"tool_result": result}

    return incidents_tool_node


def _make_inventory_tool_node(
    inventory_tool_fn: Callable[[dict[str, Any]], Any],
) -> Callable[[AgentState], Any]:
    async def inventory_tool_node(state: AgentState) -> dict[str, Any]:
        query = extract_inventory_query(state["question"])
        result = await inventory_tool_fn({"query": query})
        return {"tool_result": result}

    return inventory_tool_node


def _tool_failed_node(state: AgentState) -> dict[str, Any]:
    tool_result = state.get("tool_result") or {}
    error = tool_result.get("error", "error desconocido")
    return {"answer": f"No pude confirmar esa información en este momento ({error}). Probá de nuevo en unos minutos."}


def _tool_result_to_context_chunks(tool_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Reformatea la salida de una tool como chunks (mismo shape que un
    resultado de `retrieve()`), para que `generate_answer(question, context)`
    no necesite una firma distinta según la fuente de datos."""
    if not tool_result:
        return []

    if not tool_result.get("ok"):
        error = tool_result.get("error", "error desconocido")
        return [
            {
                "source_document": "incidents-api",
                "section": "Estado de ticket",
                "text": f"No se pudo confirmar el estado del ticket solicitado ahora mismo ({error}).",
            }
        ]

    chunks: list[dict[str, Any]] = []
    for incident in tool_result.get("incidents", []):
        text = (
            f"Ticket #{incident['id']} — {incident['title']}\n"
            f"Estado: {incident['status']}. Categoría: {incident['category']}. "
            f"Origen: {incident['origin']}. Sede: {incident['branch']}.\n"
            f"Creado: {incident['created_at']}. Actualizado: {incident['updated_at']}."
        )
        chunks.append({"source_document": "incidents-api", "section": f"Ticket {incident['id']}", "text": text})

    for product in tool_result.get("products", []):
        text = (
            f"SKU {product['sku']} — {product['name']} ({product['client_name']}).\n"
            f"Categoría: {product['category']}. Almacén: {product['warehouse']}. "
            f"Stock actual: {product['current_stock']} unidades."
        )
        chunks.append({"source_document": "incidents-api", "section": f"Inventario {product['sku']}", "text": text})

    return chunks


def _make_generate_node(
    generate_fn: Callable[[str, list[dict[str, Any]]], str],
) -> Callable[[AgentState], dict[str, Any]]:
    def generate_node(state: AgentState) -> dict[str, Any]:
        context = list(state.get("context") or [])
        tool_chunks = _tool_result_to_context_chunks(state.get("tool_result"))
        return {"answer": generate_fn(state["question"], tool_chunks + context)}

    return generate_node


def _no_context_node(state: AgentState) -> dict[str, Any]:
    return {"answer": NO_CONTEXT_ANSWER}


def _empty_question_node(state: AgentState) -> dict[str, Any]:
    return {"error": EMPTY_QUESTION_ERROR}


def _route_after_receive_question(state: AgentState) -> str:
    return "empty_question" if not state["question"] else "classify_intent"


def _route_after_classify(state: AgentState) -> str:
    return "incidents_tool" if state["route"] == "both" else state["route"]


def _route_after_incidents_tool(state: AgentState) -> str:
    if state.get("route") == "both":
        return "retrieve"
    tool_result = state.get("tool_result") or {}
    return "generate" if tool_result.get("ok") else "tool_failed"


def _route_after_inventory_tool(state: AgentState) -> str:
    tool_result = state.get("tool_result") or {}
    return "generate" if tool_result.get("ok") else "tool_failed"


def _route_after_retrieve(state: AgentState) -> str:
    context = state.get("context") or []
    tool_result = state.get("tool_result")
    tool_ok = bool(tool_result and tool_result.get("ok"))
    return "no_context" if (not context and not tool_ok) else "generate"


def build_graph(
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = generate_answer,
    classify_fn: Callable[[str], str] = classify_intent,
    incidents_tool_fn: Callable[[dict[str, Any]], Any] = _default_incidents_tool_call,
    inventory_tool_fn: Callable[[dict[str, Any]], Any] = _default_inventory_tool_call,
    checkpointer: Any = None,
) -> CompiledStateGraph:
    """Arma y compila el grafo. Todas las funciones de negocio son
    inyectables para poder probar el enrutamiento y el contrato de nodos
    sin credenciales reales de Qdrant/4Geeks ni un backend HTTP en vivo
    (ver `tests/pipelines/test_agent_graph.py`).

    `.compile()` valida la estructura del grafo y lanza una excepción clara
    si algo está mal -- no se envuelve en un try/except que la esconda.
    """
    graph = StateGraph(AgentState)

    graph.add_node("receive_question", _receive_question_node)
    graph.add_node("classify_intent", _make_classify_node(classify_fn))
    graph.add_node("retrieve", _make_retrieve_node(retrieve_fn))
    graph.add_node("incidents_tool", _make_incidents_tool_node(incidents_tool_fn))
    graph.add_node("inventory_tool", _make_inventory_tool_node(inventory_tool_fn))
    graph.add_node("generate", _make_generate_node(generate_fn))
    graph.add_node("no_context", _no_context_node)
    graph.add_node("empty_question", _empty_question_node)
    graph.add_node("tool_failed", _tool_failed_node)

    graph.add_edge(START, "receive_question")
    graph.add_conditional_edges(
        "receive_question",
        _route_after_receive_question,
        {"empty_question": "empty_question", "classify_intent": "classify_intent"},
    )
    graph.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {"rag": "retrieve", "incidents_tool": "incidents_tool", "inventory_tool": "inventory_tool"},
    )
    graph.add_conditional_edges(
        "incidents_tool",
        _route_after_incidents_tool,
        {"retrieve": "retrieve", "generate": "generate", "tool_failed": "tool_failed"},
    )
    graph.add_conditional_edges(
        "inventory_tool",
        _route_after_inventory_tool,
        {"generate": "generate", "tool_failed": "tool_failed"},
    )
    graph.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"no_context": "no_context", "generate": "generate"},
    )
    graph.add_edge("generate", END)
    graph.add_edge("no_context", END)
    graph.add_edge("empty_question", END)
    graph.add_edge("tool_failed", END)

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


async def run_agent(
    question: str,
    *,
    thread_id: str | None = None,
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = generate_answer,
    classify_fn: Callable[[str], str] = classify_intent,
    incidents_tool_fn: Callable[[dict[str, Any]], Any] = _default_incidents_tool_call,
    inventory_tool_fn: Callable[[dict[str, Any]], Any] = _default_inventory_tool_call,
    checkpointer: Any = None,
) -> tuple[AgentState, list[dict[str, Any]], str]:
    """Corre el grafo de punta a punta. Devuelve `(estado_final, trace, thread_id)`.

    `async def` porque `incidents_tool`/`inventory_tool` llaman al MCP
    Server vía `langchain-mcp-adapters` (async) -- ver docstring del módulo,
    "Migración a MCP".

    El trace es la secuencia real `[{"node": ..., "output": ...}, ...]` en
    el orden en que LangGraph ejecutó los nodos (`stream_mode="updates"`),
    guardada en disco para poder consultarla después de la corrida — y
    muestra con claridad si se usó el RAG, una tool, o ambos.
    """
    compiled_graph = build_graph(
        retrieve_fn=retrieve_fn,
        generate_fn=generate_fn,
        classify_fn=classify_fn,
        incidents_tool_fn=incidents_tool_fn,
        inventory_tool_fn=inventory_tool_fn,
        checkpointer=checkpointer,
    )
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    trace: list[dict[str, Any]] = []
    final_state: dict[str, Any] = {"question": question}

    async for update in compiled_graph.astream({"question": question}, config=config, stream_mode="updates"):
        for node_name, partial_state in update.items():
            trace.append({"node": node_name, "output": partial_state})
            final_state.update(partial_state)

    _save_trace(thread_id, trace)
    return final_state, trace, thread_id  # type: ignore[return-value]
