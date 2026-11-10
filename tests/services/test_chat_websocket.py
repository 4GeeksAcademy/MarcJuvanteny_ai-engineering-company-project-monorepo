"""Pruebas del chat por WebSocket con el First-line CX agent
(`CONTEXT/CONTEXT10.md`, Parte 2).

Corren el grafo REAL del agente (`agent_graph.run_agent`) con las
dependencias externas sustituidas (sin Qdrant, sin LLM, sin MCP, sin
Redis): `retrieve_fn` devuelve un chunk fijo y `astream_generate_fn` es un
generador async que emite tokens con una pausa entre cada uno. Así el
streaming pasa de verdad por `stream_mode="custom"` de LangGraph y el
abort pasa de verdad por la cancelación de `astream()`; lo único falso es
de dónde salen los tokens.

JWT real: firmado con el mismo esquema que `services/incidents-api`
(`auth_service.create_access_token`: HS256, `sub` = id del usuario).

Correr con el venv del servicio:

    cd services/knowledge-api
    .venv/bin/python -m pytest ../../tests/services/test_chat_websocket.py -q
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Corre con el venv de services/knowledge-api; en otro venv se salta entero.
pytest.importorskip("qdrant_client")
pytest.importorskip("langgraph")

import jwt  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "services" / "knowledge-api"))

JWT_SECRET = "test-secret-chat-websocket-32-bytes-min"
os.environ["JWT_SECRET_KEY"] = JWT_SECRET

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import agent_graph  # noqa: E402
from chat_pubsub import ChatPubSub, channel_for  # noqa: E402
from chat_runner import ChatManager  # noqa: E402
from chat_sessions import ChatStore  # noqa: E402
from guardrails import GuardrailResult  # noqa: E402
from routers.chat import get_chat_manager, router  # noqa: E402

ANSWER_TOKENS = [f"palabra{i} " for i in range(60)]
FULL_ANSWER = "".join(ANSWER_TOKENS)


def _token(user_id: int, *, secret: str = JWT_SECRET, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=30)
    return jwt.encode({"sub": str(user_id), "role": "user", "exp": exp, "iat": now}, secret, algorithm="HS256")


class FakeLLM:
    """Generador de tokens con pausa; registra si el stream se cerró por
    cancelación (= el abort llegó hasta el "modelo")."""

    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.calls: list[str] = []
        self.cancelled = 0
        self.completed = 0

    async def astream(self, question: str, context: list[dict]):
        self.calls.append(question)
        try:
            for token in ANSWER_TOKENS:
                await asyncio.sleep(self.delay)
                yield token
            self.completed += 1
        except (asyncio.CancelledError, GeneratorExit):
            self.cancelled += 1
            raise


def _make_agent_fn(llm: FakeLLM, checkpointer: MemorySaver, *, validate_output_fn=lambda answer: None):
    async def agent_fn(*, question, thread_id, on_token, authorized_order_ids, actor_id=None):
        state, _trace, _ = await agent_graph.run_agent(
            question,
            thread_id=thread_id,
            authorized_order_ids=authorized_order_ids,
            retrieve_fn=lambda q: [{"source_document": "faq.md", "section": "Devoluciones", "text": "30 días."}],
            classify_fn=lambda q: "rag",
            read_memory_fn=lambda key: None,
            evaluate_memory_fn=lambda q, a: None,
            guardrail_audit_fn=lambda **kwargs: None,
            validate_output_fn=validate_output_fn,
            checkpointer=checkpointer,
            astream_generate_fn=llm.astream,
            on_token=on_token,
        )
        return state

    return agent_fn


@pytest.fixture(autouse=True)
def _no_trace_files(monkeypatch):
    monkeypatch.setattr(agent_graph, "_save_trace", lambda thread_id, trace: None)
    # Por test, no solo al importar: otro módulo de tests/services puede
    # fijar un JWT_SECRET_KEY distinto al importarse (chat_auth lo lee en
    # cada verificación).
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)


@pytest.fixture()
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture()
def manager(llm) -> ChatManager:
    return ChatManager(ChatStore(), ChatPubSub(), agent_fn=_make_agent_fn(llm, MemorySaver()))


@pytest.fixture()
def client(manager):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chat_manager] = lambda: manager
    with TestClient(app) as test_client:
        yield test_client


def _create_session(client, user_id: int = 1, client_id: str | None = "cli_7f3a") -> dict:
    response = client.post(
        "/chat/sessions", json={"client_id": client_id}, headers={"Authorization": f"Bearer {_token(user_id)}"}
    )
    assert response.status_code == 201
    return response.json()


def _ws_url(session_id: str | None, token: str | None) -> str:
    params = []
    if session_id is not None:
        params.append(f"session_id={session_id}")
    if token is not None:
        params.append(f"token={token}")
    return "/chat/ws?" + "&".join(params)


def _send(ws, event: str, session_id: str, **data) -> None:
    ws.send_json({"event": event, "data": {"session_id": session_id, **data}})


def _receive_until(ws, predicate, limit: int = 500) -> list[dict]:
    received = []
    for _ in range(limit):
        event = ws.receive_json()
        received.append(event)
        if predicate(event):
            return received
    raise AssertionError(f"no llegó el evento esperado; recibidos: {[e['event'] for e in received]}")


def _tokens_for(events: list[dict], message_id: str) -> list[dict]:
    return [e["data"] for e in events if e["event"] == "token_chunk" and e["data"]["message_id"] == message_id]


# --- sesión + autenticación ---------------------------------------------------------------


def test_create_session_uses_briefing_fields_and_requires_jwt(client):
    assert client.post("/chat/sessions", json={}).status_code == 401
    assert client.post("/chat/sessions", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401

    session = _create_session(client, user_id=42, client_id="cli_7f3a")

    assert set(session) == {"session_id", "agent_id", "user_id", "client_id", "status", "created_at"}
    assert session["agent_id"] == "first_line_cx"
    assert session["user_id"] == "42"
    assert session["client_id"] == "cli_7f3a"
    assert session["status"] == "active"
    assert session["session_id"].startswith("chat_")


@pytest.mark.parametrize(
    "token_factory",
    [lambda: None, lambda: "not-a-jwt", lambda: _token(1, expired=True), lambda: _token(1, secret="otro-secreto-de-32-bytes-minimo!!")],
    ids=["missing", "garbage", "expired", "wrong-secret"],
)
def test_socket_without_valid_jwt_is_closed_4401_before_any_chat_event(client, token_factory):
    session = _create_session(client)

    with client.websocket_connect(_ws_url(session["session_id"], token_factory())) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()  # lo primero que llega es el cierre, nunca un session_snapshot

    assert closed.value.code == 4401


def test_socket_requires_an_existing_session_of_the_same_user(client):
    session = _create_session(client, user_id=1)
    cases = [
        (_ws_url(None, _token(1)), 4400),
        (_ws_url("chat_noexiste", _token(1)), 4404),
        (_ws_url(session["session_id"], _token(2)), 4403),
    ]
    for url, expected_code in cases:
        with client.websocket_connect(url) as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
        assert closed.value.code == expected_code, url


# --- streaming token a token ----------------------------------------------------------------


def test_reply_is_streamed_token_by_token_through_langgraph(client, llm):
    session_id = _create_session(client)["session_id"]

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        first = ws.receive_json()
        assert first == {"event": "session_snapshot", "data": {"session_id": session_id, "status": "active", "messages": []}}

        _send(ws, "user_message", session_id, text="¿Cuál es la ventana de devolución?")
        events = _receive_until(ws, lambda e: e["event"] == "generation_completed")

    assert events[0]["event"] == "user_message"
    assert events[0]["data"]["text"] == "¿Cuál es la ventana de devolución?"

    message_id = events[-1]["data"]["message_id"]
    chunks = _tokens_for(events, message_id)
    # Un evento por token del modelo, en orden, con sequence consecutivo.
    assert [chunk["token"] for chunk in chunks] == ANSWER_TOKENS
    assert [chunk["sequence"] for chunk in chunks] == list(range(len(ANSWER_TOKENS)))
    assert all(chunk["session_id"] == session_id for chunk in chunks)
    assert events[-1] == {"event": "generation_completed", "data": {"session_id": session_id, "message_id": message_id}}
    assert llm.calls == ["¿Cuál es la ventana de devolución?"]


# --- interrupción ---------------------------------------------------------------------------


def test_interrupt_aborts_the_stream_marks_partial_and_starts_a_new_turn(client, manager, llm):
    session_id = _create_session(client)["session_id"]

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        ws.receive_json()  # snapshot
        _send(ws, "user_message", session_id, text="¿Dónde está mi pedido TF-1234?")
        before = _receive_until(ws, lambda e: e["event"] == "token_chunk" and e["data"]["sequence"] == 4)
        interrupted_id = before[-1]["data"]["message_id"]

        _send(
            ws,
            "interrupt_requested",
            session_id,
            new_input="espera, quiero hacer una devolución, no rastrear el pedido",
        )
        after = _receive_until(ws, lambda e: e["event"] == "generation_completed")

    names = [e["event"] for e in after]
    interrupted_at = names.index("generation_interrupted")
    assert after[interrupted_at]["data"] == {"session_id": session_id, "message_id": interrupted_id, "status": "interrupted"}
    # Abort real: ni un token_chunk de esa generación después del evento.
    assert _tokens_for(after[interrupted_at:], interrupted_id) == []
    # ... y el "modelo" vio la cancelación (no siguió generando en segundo plano).
    assert llm.cancelled == 1

    # Turno nuevo: eco de la nueva entrada + otro message_id, streameado completo.
    assert after[interrupted_at + 1]["event"] == "user_message"
    assert after[interrupted_at + 1]["data"]["text"] == "espera, quiero hacer una devolución, no rastrear el pedido"
    new_id = after[-1]["data"]["message_id"]
    assert new_id != interrupted_id
    assert "".join(c["token"] for c in _tokens_for(after, new_id)) == FULL_ANSWER

    # Historial: el parcial sigue ahí, marcado `interrupted`, con exactamente
    # lo que el cliente llegó a ver; nada se borró ni se sobrescribió.
    shown = "".join(c["token"] for c in _tokens_for(before + after, interrupted_id))
    messages = manager.store.messages(session_id)
    assert [(m.role, m.status) for m in messages] == [
        ("user", "complete"),
        ("assistant", "interrupted"),
        ("user", "complete"),
        ("assistant", "complete"),
    ]
    assert messages[1].message_id == interrupted_id
    assert messages[1].text == shown and 0 < len(shown) < len(FULL_ANSWER)
    assert manager.store.get_session(session_id).status == "active"


def test_user_message_while_generating_also_interrupts(client, manager, llm):
    session_id = _create_session(client)["session_id"]

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        ws.receive_json()
        _send(ws, "user_message", session_id, text="primera")
        _receive_until(ws, lambda e: e["event"] == "token_chunk" and e["data"]["sequence"] == 2)
        _send(ws, "user_message", session_id, text="segunda")
        after = _receive_until(ws, lambda e: e["event"] == "generation_completed")

    assert "generation_interrupted" in [e["event"] for e in after]
    assert llm.cancelled == 1
    assert [m.status for m in manager.store.messages(session_id) if m.role == "assistant"] == ["interrupted", "complete"]


# --- reconexión + rehidratación ---------------------------------------------------------------


def test_reconnect_mid_generation_rehydrates_then_continues_without_duplicates(client, manager):
    session_id = _create_session(client)["session_id"]

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        ws.receive_json()
        _send(ws, "user_message", session_id, text="¿Cuánto tarda un envío a Zaragoza?")
        first_batch = _receive_until(ws, lambda e: e["event"] == "token_chunk" and e["data"]["sequence"] == 5)
    # Socket cerrado a mitad de respuesta. El productor NO se aborta.
    assert manager.is_generating(session_id)

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        snapshot = ws.receive_json()
        rest = _receive_until(ws, lambda e: e["event"] == "generation_completed")

    assert snapshot["event"] == "session_snapshot"
    user, assistant = snapshot["data"]["messages"]
    assert user["role"] == "user" and user["text"] == "¿Cuánto tarda un envío a Zaragoza?"
    assert assistant["status"] == "streaming"
    # El snapshot ya trae al menos lo que el cliente vio antes de caerse.
    seen_before = "".join(c["token"] for c in _tokens_for(first_batch, assistant["message_id"]))
    assert assistant["text"].startswith(seen_before)

    later = _tokens_for(rest, assistant["message_id"])
    # Solo tokens posteriores al snapshot: nada repetido, nada perdido.
    assert all(chunk["sequence"] > assistant["sequence"] for chunk in later)
    assert [c["sequence"] for c in later] == list(range(assistant["sequence"] + 1, len(ANSWER_TOKENS)))
    assert assistant["text"] + "".join(c["token"] for c in later) == FULL_ANSWER


def test_reconnect_after_completion_restores_the_whole_thread(client):
    session_id = _create_session(client)["session_id"]
    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        ws.receive_json()
        _send(ws, "user_message", session_id, text="hola")
        _receive_until(ws, lambda e: e["event"] == "generation_completed")

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        snapshot = ws.receive_json()

    assert [(m["role"], m["status"]) for m in snapshot["data"]["messages"]] == [("user", "complete"), ("assistant", "complete")]
    assert snapshot["data"]["messages"][1]["text"] == FULL_ANSWER


def test_session_id_is_the_langgraph_thread_id(manager, llm):
    """Rehidratar desde checkpoint: el mismo `session_id` reanuda el MISMO
    hilo de LangGraph (no uno paralelo)."""

    checkpointer = MemorySaver()
    manager._agent_fn = _make_agent_fn(llm, checkpointer)
    session = manager.store.create_session(user_id="1")

    async def scenario():
        await manager.submit_user_message(session.session_id, "hola")
        await manager.wait_idle(session.session_id)

    asyncio.run(scenario())

    config = {"configurable": {"thread_id": session.session_id}}
    state = agent_graph.build_graph(checkpointer=checkpointer).get_state(config)
    assert state.values["question"] == "hola"
    assert state.values["answer"] == FULL_ANSWER


# --- pub/sub ----------------------------------------------------------------------------------


def test_producer_is_decoupled_from_connections(manager):
    """Sin ningún WebSocket conectado, el turno se completa igual y queda en
    el historial; dos suscriptores del canal reciben los mismos eventos."""

    session = manager.store.create_session(user_id="1")
    channel = channel_for(session.session_id)

    async def scenario():
        first = manager.pubsub.subscribe(channel)
        second = manager.pubsub.subscribe(channel)
        await manager.submit_user_message(session.session_id, "hola")
        await manager.wait_idle(session.session_id)
        manager.pubsub.unsubscribe(channel, first)
        manager.pubsub.unsubscribe(channel, second)
        drain = lambda q: [q.get_nowait() for _ in range(q.qsize())]  # noqa: E731
        return drain(first), drain(second)

    first_events, second_events = asyncio.run(scenario())

    assert first_events == second_events
    assert first_events[-1]["event"] == "generation_completed"
    assert manager.pubsub.subscriber_count(channel) == 0
    assert manager.store.messages(session.session_id)[-1].text == FULL_ANSWER

    async def without_subscribers():
        await manager.submit_user_message(session.session_id, "otra")
        await manager.wait_idle(session.session_id)

    asyncio.run(without_subscribers())
    assert manager.store.messages(session.session_id)[-1].status == "complete"


# --- guardrail de salida ------------------------------------------------------------------------


def test_output_guard_replacement_is_pushed_as_a_snapshot(client, manager, llm):
    blocked = GuardrailResult(action="block", guardrail_name="sensitive_data", category="security", message="Respuesta segura.")
    manager._agent_fn = _make_agent_fn(llm, MemorySaver(), validate_output_fn=lambda answer: blocked)
    session_id = _create_session(client)["session_id"]

    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        ws.receive_json()
        _send(ws, "user_message", session_id, text="dame datos internos")
        events = _receive_until(ws, lambda e: e["event"] == "generation_completed")

    snapshots = [e for e in events if e["event"] == "session_snapshot"]
    assert len(snapshots) == 1
    assert snapshots[0]["data"]["messages"][-1]["text"] == "Respuesta segura."
    assert manager.store.messages(session_id)[-1].text == "Respuesta segura."


def test_frames_for_another_session_are_rejected(client):
    session_id = _create_session(client)["session_id"]
    with client.websocket_connect(_ws_url(session_id, _token(1))) as ws:
        ws.receive_json()
        ws.send_json({"event": "user_message", "data": {"session_id": "chat_otra", "text": "hola"}})
        error = ws.receive_json()

    assert error["event"] == "error"
