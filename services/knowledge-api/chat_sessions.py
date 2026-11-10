"""Entidad de sesión de chat (`CONTEXT/CONTEXT10.md`, Parte 2, §3) + su
historial de mensajes.

`ChatSession` usa EXACTAMENTE los campos del BRIEFING: `session_id`,
`agent_id` (`first_line_cx`), `user_id`, `client_id`, `status` (`active`,
`interrupted`, `closed`), `created_at`. El `session_id` es además el
`thread_id` de LangGraph del agente (`agent_graph._DEFAULT_CHECKPOINTER`):
un solo id para la misma sesión, nunca uno paralelo.

El historial (`ChatMessage`) es lo que el agente NO guarda -- su
`AgentState` resuelve una pregunta por corrida, sin historial (ver
`agent_graph.py`, "Estado del grafo") -- y es lo que `session_snapshot`
devuelve al reconectar. Un mensaje del asistente interrumpido se queda en
el historial con `status = "interrupted"` y el texto ya mostrado; nunca se
borra ni se sobrescribe.

En memoria, mismo criterio que `chat_pubsub.py` y que el `MemorySaver` del
agente: sobrevive a reconexiones del WebSocket, no a un reinicio del
proceso.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

AGENT_ID = "first_line_cx"


class ChatSessionStatus(StrEnum):
    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    CLOSED = "closed"


MessageStatus = Literal["complete", "streaming", "interrupted"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: f"chat_{uuid.uuid4().hex[:12]}")
    agent_id: str = AGENT_ID
    user_id: str
    client_id: str | None = None
    status: ChatSessionStatus = ChatSessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=_now)


class ChatMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    role: Literal["user", "assistant"]
    text: str = ""
    status: MessageStatus = "complete"
    # Último `sequence` de `token_chunk` ya aplicado a `text` (-1 = ninguno).
    # El cliente lo usa al rehidratar para descartar tokens repetidos.
    sequence: int = -1
    created_at: datetime = Field(default_factory=_now)


class ChatStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, list[ChatMessage]] = {}

    def create_session(self, user_id: str, client_id: str | None = None) -> ChatSession:
        session = ChatSession(user_id=user_id, client_id=client_id)
        self._sessions[session.session_id] = session
        self._messages[session.session_id] = []
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def add_message(self, session_id: str, message: ChatMessage) -> ChatMessage:
        self._messages[session_id].append(message)
        return message

    def messages(self, session_id: str) -> list[ChatMessage]:
        return list(self._messages.get(session_id, []))

    def snapshot(self, session_id: str) -> dict[str, Any]:
        """`data` de `session_snapshot` -- el historial completo, incluido
        un mensaje del asistente todavía en `streaming` con el texto que
        lleva hasta ahora."""

        session = self._sessions[session_id]
        return {
            "session_id": session_id,
            "status": session.status.value,
            "messages": [message.model_dump(mode="json") for message in self._messages[session_id]],
        }
