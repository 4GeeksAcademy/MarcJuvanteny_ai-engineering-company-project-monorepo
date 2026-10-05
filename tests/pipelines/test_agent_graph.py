"""Evals del grafo del agente RAG de TrackFlow (`CONTEXT/CONTEXT7.md`,
sección "Grafo del agente" / "Tracing y evaluación").

Corren sin conexión: `retrieve_fn`/`generate_fn` inyectados (fakes
deterministas, mismo patrón que `tests/pipelines/test_rag.py`) para los
casos de enrutamiento, y un `retrieve()` real contra Qdrant `:memory:` +
un embedding léxico local (reutilizado de `data/eval/evaluate_retrieval.py`,
no un modelo real de 4Geeks) para el eval de anclaje. Cada test corre el
grafo **una vez** (inyectando fakes, no llamando a ningún servicio externo)
y hace las aserciones sobre el `trace`/estado resultante de esa corrida — no
sobre una ejecución en vivo repetida.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "services" / "knowledge-api"))

import agent_graph  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

# data/process/rag.py -- para setup()/chunk_document() en el eval de anclaje.
# Mismo motivo de colision de nombres ("rag.py" x2) que ya documentan
# data/pipelines/rag.py y tests/pipelines/test_rag.py.
_INDEXING_PATH = ROOT_DIR / "data" / "process" / "rag.py"
_indexing_spec = importlib.util.spec_from_file_location("trackflow_rag_indexing_agent_eval", _INDEXING_PATH)
indexing = importlib.util.module_from_spec(_indexing_spec)
sys.modules["trackflow_rag_indexing_agent_eval"] = indexing
_indexing_spec.loader.exec_module(indexing)

from qdrant_client import QdrantClient  # noqa: E402


# --- Fakes deterministas (sin red) -----------------------------------------


def _echo_generate(question: str, context: list[dict]) -> str:
    """Simula un LLM "fiel": la respuesta es literalmente el texto de los
    chunks recuperados. Sirve para verificar anclaje sin pretender simular
    la calidad de un modelo real (ver el eval de anclaje más abajo)."""
    return " ".join(chunk["text"] for chunk in context)


def _refuse_to_be_called(*args, **kwargs):
    raise AssertionError("esta funcion no deberia haberse llamado en este escenario")


# --- Estructura del grafo ----------------------------------------------------


def test_compile_fails_clearly_on_structural_error():
    """"Compila el grafo... debe fallar clara si hay un error estructural"
    -- una arista hacia un nodo nunca definido con add_node()."""
    broken = StateGraph(agent_graph.AgentState)
    broken.add_node("receive_question", lambda s: s)
    broken.add_edge(START, "receive_question")
    broken.add_edge("receive_question", "nodo_que_no_existe")  # nunca definido

    with pytest.raises(ValueError, match="unknown node"):
        broken.compile()


def test_valid_graph_compiles_without_error():
    compiled = agent_graph.build_graph()
    assert compiled is not None


# --- Eval 1: orden del trace en el camino feliz -----------------------------


@pytest.mark.anyio
async def test_eval_retrieve_executes_before_generate_in_the_trace():
    """"Para esta pregunta, el nodo retrieve debe ejecutarse antes que
    generate" -- el ejemplo literal de la guía, verificado sobre el trace."""

    def fake_retrieve(question: str):
        return [{"source_document": "sla-delivery", "section": "Resumen", "text": "texto de ejemplo"}]

    state, trace, thread_id = await agent_graph.run_agent(
        "¿cuál es el SLA de entrega?", retrieve_fn=fake_retrieve, generate_fn=_echo_generate
    )

    node_order = [step["node"] for step in trace]
    assert node_order == [
        "receive_question",
        "input_guard",
        "classify_intent",
        "retrieve_memory",
        "retrieve",
        "generate",
        "output_guard",
        "propose_memory",
    ]
    assert node_order.index("retrieve") < node_order.index("generate")
    assert state["answer"] == "texto de ejemplo"

    # El trace debe quedar consultable despues de la corrida, no solo en consola.
    persisted = agent_graph.get_trace(thread_id)
    assert persisted == trace


# --- Eval 2: pregunta vacia -> error, sin llamar a retrieve -----------------


@pytest.mark.anyio
async def test_eval_empty_question_routes_to_error_without_calling_retrieve():
    state, trace, _thread_id = await agent_graph.run_agent(
        "   ", retrieve_fn=_refuse_to_be_called, generate_fn=_refuse_to_be_called
    )

    node_order = [step["node"] for step in trace]
    assert node_order == ["receive_question", "input_guard", "empty_question"]
    assert state["error"] == agent_graph.EMPTY_QUESTION_ERROR
    assert "answer" not in state or state.get("answer") is None


# --- Eval 3: sin contexto por encima del umbral -> honestidad, sin generar -


@pytest.mark.anyio
async def test_eval_no_context_routes_to_honest_answer_without_calling_generate():
    def fake_retrieve_nothing(question: str):
        return []

    state, trace, _thread_id = await agent_graph.run_agent(
        "¿algo totalmente fuera de la base de conocimiento?",
        retrieve_fn=fake_retrieve_nothing,
        generate_fn=_refuse_to_be_called,
    )

    node_order = [step["node"] for step in trace]
    assert node_order == [
        "receive_question",
        "input_guard",
        "classify_intent",
        "retrieve_memory",
        "retrieve",
        "no_context",
        "output_guard",
        "propose_memory",
    ]
    assert state["answer"] == agent_graph.NO_CONTEXT_ANSWER


# --- Eval 4 (anclaje): la respuesta sigue anclada a la base de conocimiento -


FAKE_VECTOR_SIZE = 16


def _lexical_embed_for_corpus() -> tuple[callable, QdrantClient, str]:
    """Mismo embedding lexico local de data/eval/evaluate_retrieval.py,
    reconstruido acá para no acoplar este test a ese script -- indexa los 4
    documentos reales en un Qdrant :memory: nuevo."""
    import math
    import re
    from collections import Counter

    token_re = re.compile(r"[a-záéíóúñü]+")

    def tokenize(text: str) -> list[str]:
        return token_re.findall(text.lower())

    all_texts = [
        chunk.text for path in sorted(indexing.KNOWLEDGE_BASE_DIR.glob("*.md")) for chunk in indexing.chunk_document(path)
    ]
    question = "¿puede un account manager ofrecer un descuento de almacenamiento sin aprobación?"
    vocabulary = sorted({token for text in [*all_texts, question] for token in tokenize(text)})
    index = {word: position for position, word in enumerate(vocabulary)}

    def embed(text: str) -> list[float]:
        counts = Counter(tokenize(text))
        vector = [0.0] * len(vocabulary)
        for word, count in counts.items():
            position = index.get(word)
            if position is not None:
                vector[position] = float(count)
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    client = QdrantClient(":memory:")
    collection = "test_trackflow_knowledge_agent_eval"
    indexing.setup(qdrant_client=client, embed_fn=embed, collection_name=collection)
    return embed, client, collection


@pytest.mark.anyio
async def test_eval_answer_stays_anchored_to_the_real_knowledge_base():
    """"Al menos un eval debe verificar que la respuesta sigue anclada en tu
    base de conocimiento existente" -- pregunta de política conocida
    (descuentos de almacenamiento) debe devolver la entidad esperada de
    `docs/company-knowledge-base/trackflow-storage-pricing.es.md`
    ("Miguel Torres"). Usa retrieve() REAL (Qdrant :memory: + el embedding
    léxico, no mockeado) -- solo generate_fn es un fake ("fiel", ver
    _echo_generate), para no depender de credenciales de 4Geeks."""
    embed, client, collection = _lexical_embed_for_corpus()

    # Import perezoso de data/pipelines/rag.py con el mismo patron de
    # importlib que el resto del RAG, para reusar retrieve() real.
    pipeline_spec = importlib.util.spec_from_file_location(
        "trackflow_rag_pipeline_agent_eval", ROOT_DIR / "data" / "pipelines" / "rag.py"
    )
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    sys.modules["trackflow_rag_pipeline_agent_eval"] = pipeline
    pipeline_spec.loader.exec_module(pipeline)

    def retrieve_fn(question: str):
        return pipeline.retrieve(question, qdrant_client=client, embed_fn=embed, collection_name=collection, min_score=-1.0)

    question = "¿puede un account manager ofrecer un descuento de almacenamiento sin aprobación?"
    state, trace, _thread_id = await agent_graph.run_agent(question, retrieve_fn=retrieve_fn, generate_fn=_echo_generate)

    assert [step["node"] for step in trace] == [
        "receive_question",
        "input_guard",
        "classify_intent",
        "retrieve_memory",
        "retrieve",
        "generate",
        "output_guard",
        "propose_memory",
    ]
    assert any("Miguel Torres" in chunk["text"] for chunk in state["context"]), (
        "el contexto recuperado no incluye la entidad esperada (Miguel Torres) -- "
        "la respuesta no puede estar anclada si el contexto ya no lo esta"
    )
    assert "Miguel Torres" in state["answer"]  # la respuesta final tambien la conserva (echo fiel del contexto)


# --- Enrutamiento: tool vs. RAG (CONTEXT7.md, "Tracing y evaluación") ------


@pytest.mark.anyio
async def test_eval_ticket_question_resolves_with_tool_not_rag():
    """"Una pregunta que debe resolverse con una tool (no con el RAG)".

    `incidents_tool_fn` ahora es `Callable[[dict], Awaitable[dict]]` -- el
    mismo contrato que `mcp_client.call_mcp_tool` (ver "Migración a MCP" en
    `agent_graph.py`), un fake async en vez del `IncidentToolOutput`
    tipado de la implementación HTTP directa ya eliminada."""

    async def fake_incidents_tool(args: dict) -> dict:
        assert args == {"query": {"incident_id": 42}}
        return {
            "ok": True,
            "incidents": [
                {
                    "id": 42,
                    "title": "Paquete perdido",
                    "status": "open",
                    "category": "lost_parcel",
                    "origin": "customer",
                    "branch": "la_warehouse",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
            "error": None,
        }

    state, trace, _thread_id = await agent_graph.run_agent(
        "¿cuál es el estado del ticket 42?",
        incidents_tool_fn=fake_incidents_tool,
        generate_fn=_echo_generate,
        retrieve_fn=_refuse_to_be_called,  # el RAG NUNCA debe llamarse en esta ruta
    )

    node_order = [step["node"] for step in trace]
    assert node_order == [
        "receive_question",
        "input_guard",
        "classify_intent",
        "retrieve_memory",
        "incidents_tool",
        "generate",
        "output_guard",
        "propose_memory",
    ]
    assert "retrieve" not in node_order
    assert state["route"] == "incidents_tool"
    assert "open" in state["answer"]


@pytest.mark.anyio
async def test_eval_policy_question_resolves_with_rag_not_tool():
    """"Una pregunta que debe resolverse con el RAG (no con una tool)"."""

    def fake_retrieve(question: str):
        return [{"source_document": "sla-delivery", "section": "Resumen", "text": "texto de politica"}]

    state, trace, _thread_id = await agent_graph.run_agent(
        "¿cuál es el SLA de entrega estándar?",
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,  # ninguna tool debe llamarse en esta ruta
        inventory_tool_fn=_refuse_to_be_called,
    )

    node_order = [step["node"] for step in trace]
    assert node_order == [
        "receive_question",
        "input_guard",
        "classify_intent",
        "retrieve_memory",
        "retrieve",
        "generate",
        "output_guard",
        "propose_memory",
    ]
    assert "incidents_tool" not in node_order and "inventory_tool" not in node_order
    assert state["route"] == "rag"
    assert state["answer"] == "texto de politica"


@pytest.mark.anyio
async def test_eval_incidents_service_unavailable_falls_back_honestly():
    """(Opcional) Fallback cuando el MCP Server no está disponible: se usa
    `mcp_client.call_mcp_tool` REAL (no un fake a mano) apuntado a un puerto
    donde nada escucha -- un `ConnectError` real de verdad, no simulado --
    y el agente responde con honestidad, sin llamar nunca al modelo de
    generación."""
    from mcp_client import build_mcp_client, call_mcp_tool

    def unreachable_client_factory():
        return build_mcp_client(url="http://127.0.0.1:1/mcp", token="", timeout=1.0)

    async def incidents_tool_against_down_mcp_server(args: dict) -> dict:
        return await call_mcp_tool("query_incident_tool", args, client_factory=unreachable_client_factory)

    state, trace, _thread_id = await agent_graph.run_agent(
        "¿cuál es el estado del ticket 7?",
        incidents_tool_fn=incidents_tool_against_down_mcp_server,
        generate_fn=_refuse_to_be_called,  # nunca debe inventar un estado llamando al LLM
        retrieve_fn=_refuse_to_be_called,
    )

    node_order = [step["node"] for step in trace]
    assert node_order == [
        "receive_question",
        "input_guard",
        "classify_intent",
        "retrieve_memory",
        "incidents_tool",
        "tool_failed",
    ]
    assert state["tool_result"]["ok"] is False
    assert "connection_error" in state["tool_result"]["error"]
    assert "No pude confirmar" in state["answer"]  # honesto, no inventa un estado


# --- Checkpointing: la corrida queda inspeccionable -------------------------


@pytest.mark.anyio
async def test_checkpointed_run_is_inspectable_via_state_history():
    """"Implementa checkpointing en cada transición de estado relevante,
    para que una corrida pueda inspeccionarse o retomarse"."""
    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver()

    def fake_retrieve(question: str):
        return [{"source_document": "sla-delivery", "section": "Resumen", "text": "contexto de prueba"}]

    compiled = agent_graph.build_graph(retrieve_fn=fake_retrieve, generate_fn=_echo_generate, checkpointer=checkpointer)
    thread_id = "test-thread-checkpointing"
    config = {"configurable": {"thread_id": thread_id}}

    await compiled.ainvoke({"question": "¿cuál es el SLA de entrega?"}, config=config)

    history = list(compiled.get_state_history(config))
    assert len(history) >= 2  # al menos el estado inicial y el final quedaron como checkpoints separados

    final_snapshot = history[0]  # get_state_history devuelve del mas reciente al mas viejo
    assert final_snapshot.values.get("answer") == "contexto de prueba"
