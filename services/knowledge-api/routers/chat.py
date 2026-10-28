"""Chat en tiempo real con el First-line CX agent (`CONTEXT/CONTEXT10.md`,
Parte 2) -- los consumidores del pub/sub (`chat_pubsub.py`).

- `POST /chat/sessions` (Bearer JWT) crea una `ChatSession` y devuelve su
  `session_id`.
- `WS /chat/ws?session_id=<id>&token=<JWT>`: una conexión persistente por
  sesión de chat. El navegador no puede poner `Authorization` en el
  handshake de un WebSocket, así que el JWT va en `?token=`. `session_id`
  es obligatorio y debe ser una sesión EXISTENTE del mismo usuario: el
  socket queda ligado a ese hilo (que es también el `thread_id` de
  LangGraph del agente).

Rechazo ANTES de cualquier evento de chat: se acepta el handshake solo para
poder cerrar con un código que el navegador sí puede leer (un rechazo en el
handshake le llega como 1006 genérico), y se cierra sin enviar nada:

    4401  sin token / token inválido o expirado  (el cliente NO reintenta)
    4400  falta session_id
    4403  la sesión es de otro usuario
    4404  la sesión no existe
    4410  la sesión está cerrada

Una vez aceptado: primero `session_snapshot` (rehidratación: historial +
mensaje en curso con su `sequence`), después los eventos en vivo del canal
`chat.<session_id>`. Cerrar el socket NO aborta la generación: el productor
sigue y el texto queda en el historial para el próximo snapshot. Solo
`interrupt_requested` (o un `user_message` nuevo) aborta.

Cliente -> servidor:
    {"event": "user_message",        "data": {"session_id": ..., "text": ...}}
    {"event": "interrupt_requested", "data": {"session_id": ..., "new_input": ...}}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict

from chat_auth import require_bearer_user, user_id_from_token
from chat_pubsub import ChatPubSub, channel_for
from chat_runner import ChatManager
from chat_sessions import ChatSessionStatus, ChatStore

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("chat")

CLOSE_UNAUTHORIZED = 4401
CLOSE_BAD_REQUEST = 4400
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_SESSION_CLOSED = 4410

_CHAT_MANAGER = ChatManager(ChatStore(), ChatPubSub())


def get_chat_manager() -> ChatManager:
    return _CHAT_MANAGER


class CreateChatSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str | None = None


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    payload: CreateChatSessionRequest | None = None,
    user_id: str = Depends(require_bearer_user),
    manager: ChatManager = Depends(get_chat_manager),
) -> dict[str, Any]:
    session = manager.store.create_session(user_id=user_id, client_id=payload.client_id if payload else None)
    return session.model_dump(mode="json")


@router.post("/sessions/{session_id}/close")
async def close_chat_session(
    session_id: str,
    user_id: str = Depends(require_bearer_user),
    manager: ChatManager = Depends(get_chat_manager),
) -> dict[str, Any]:
    session = manager.store.get_session(session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    await manager.close_session(session_id)
    return session.model_dump(mode="json")


def _error(session_id: str, detail: str) -> dict[str, Any]:
    return {"event": "error", "data": {"session_id": session_id, "detail": detail}}


async def _forward_events(websocket: WebSocket, queue: asyncio.Queue[dict[str, Any] | None], snapshot: dict[str, Any]) -> None:
    # Tokens que ya vienen incluidos en el snapshot (llegaron a la cola
    # entre el subscribe y el armado del snapshot) no se reenvían.
    applied = {message["message_id"]: message["sequence"] for message in snapshot["messages"]}
    while True:
        event = await queue.get()
        if event is None:
            await websocket.close(code=CLOSE_SESSION_CLOSED)
            return
        if event["event"] == "token_chunk":
            data = event["data"]
            if data["sequence"] <= applied.get(data["message_id"], -1):
                continue
        await websocket.send_json(event)


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str | None = Query(default=None),
    token: str | None = Query(default=None),
    manager: ChatManager = Depends(get_chat_manager),
) -> None:
    await websocket.accept()

    user_id = user_id_from_token(token)
    if user_id is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED, reason="Not authenticated.")
        return
    if not session_id:
        await websocket.close(code=CLOSE_BAD_REQUEST, reason="session_id is required.")
        return
    session = manager.store.get_session(session_id)
    if session is None:
        await websocket.close(code=CLOSE_NOT_FOUND, reason="Chat session not found.")
        return
    if session.user_id != user_id:
        await websocket.close(code=CLOSE_FORBIDDEN, reason="Chat session belongs to another user.")
        return
    if session.status == ChatSessionStatus.CLOSED:
        await websocket.close(code=CLOSE_SESSION_CLOSED, reason="Chat session is closed.")
        return

    channel = channel_for(session_id)
    # Suscribirse ANTES de armar el snapshot: ningún token puede caer en el
    # hueco entre los dos (los repetidos se filtran por `sequence`).
    queue = manager.pubsub.subscribe(channel)
    snapshot = manager.store.snapshot(session_id)
    forwarder: asyncio.Task[None] | None = None
    try:
        await websocket.send_json({"event": "session_snapshot", "data": snapshot})
        forwarder = asyncio.create_task(_forward_events(websocket, queue, snapshot))

        while True:
            frame = await websocket.receive_json()
            event = frame.get("event") if isinstance(frame, dict) else None
            data = frame.get("data") if isinstance(frame, dict) else None
            if not isinstance(data, dict) or data.get("session_id") != session_id:
                # Al mismo `queue` que el forwarder: un solo escritor del socket.
                queue.put_nowait(_error(session_id, "Each frame must carry this connection's session_id."))
                continue

            if event == "user_message":
                await manager.submit_user_message(session_id, str(data.get("text") or ""))
            elif event == "interrupt_requested":
                await manager.interrupt(session_id, data.get("new_input"))
            else:
                queue.put_nowait(_error(session_id, f"Unsupported event: {event!r}."))
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: el forwarder ya cerró el socket (sesión cerrada).
        pass
    except ValueError:
        logger.info("chat %s: frame no-JSON, se cierra la conexión", session_id)
        await websocket.close(code=CLOSE_BAD_REQUEST, reason="Frames must be JSON.")
    finally:
        manager.pubsub.unsubscribe(channel, queue)
        if forwarder is not None:
            forwarder.cancel()
