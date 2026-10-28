"""Productor del chat por WebSocket (`CONTEXT/CONTEXT10.md`, Parte 2): corre
un turno del First-line CX agent (`agent_graph.run_agent`, sin cambiar su
lógica ni sus tools) y publica lo que pasa en `chat.<session_id>`
(`chat_pubsub.py`). Nunca toca un WebSocket.

Eventos que publica (`{"event": ..., "data": {...}}`, CONTEXT10.md §4):

- `user_message`           {session_id, message_id, text} -- eco del turno del usuario
- `token_chunk`            {session_id, message_id, token, sequence}
- `generation_interrupted` {session_id, message_id, status: "interrupted"}
- `generation_completed`   {session_id, message_id}
- `session_snapshot`       {session_id, status, messages} -- solo si el texto
  final difiere de lo ya emitido (ver "Guardrail de salida" abajo)

## Abort real del stream

Cada turno corre en su propia `asyncio.Task`. Una interrupción
(`interrupt_requested`, o un `user_message` nuevo mientras el agente sigue
respondiendo) hace `task.cancel()`: la cancelación entra en el
`astream()` de LangGraph y en el `async for` del stream del LLM
(`rag.py::astream_answer`), que cierra la conexión HTTP del modelo. Como
los `token_chunk` solo se publican desde esa tarea, después del cancel no
puede salir ningún token más de esa generación. NO se usa `interrupt()` de
LangGraph para esto: eso es una pausa HITL del grafo, no un abort.

Después del abort: el mensaje parcial queda en el historial con `status =
"interrupted"` y los tokens ya mostrados, la sesión pasa a `interrupted`,
se publica `generation_interrupted`, y la nueva entrada del usuario arranca
un turno NUEVO (mensaje nuevo, `message_id` nuevo) -- el interrumpido nunca
se borra ni se reescribe.

## Guardrail de salida

`output_guard`/`propose_memory` corren DESPUÉS de `generate`, así que la
respuesta final puede ser lo streameado + un sufijo (redirección, propuesta
de memoria) o un reemplazo completo (fuga de datos sensibles). Si es un
sufijo, se emite como más `token_chunk`. Si es un reemplazo, el historial
guarda el texto final (el seguro) y se publica un `session_snapshot` para
que todos los clientes reemplacen lo que mostraron. Las rutas sin LLM
(`no_context`, `guardrail_blocked`, `tool_failed`) no streamean nada desde
el modelo: su respuesta completa se emite como `token_chunk` por palabra.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from chat_pubsub import ChatPubSub, channel_for
from chat_sessions import ChatMessage, ChatSessionStatus, ChatStore
from order_access import authorized_order_ids_for

logger = logging.getLogger("chat")

AgentFn = Callable[..., Awaitable[dict[str, Any]]]

FAILURE_ANSWER = "No se pudo generar una respuesta en este momento."

_TOKEN_SPLIT = re.compile(r"\S+\s*|\s+")


def split_into_tokens(text: str) -> list[str]:
    return _TOKEN_SPLIT.findall(text)


async def default_agent_fn(
    *,
    question: str,
    thread_id: str,
    on_token: Callable[[str], Awaitable[None]],
    authorized_order_ids: list[str],
) -> dict[str, Any]:
    from agent_graph import astream_generate_with_agent_prompt, run_agent

    state, _trace, _thread_id = await run_agent(
        question,
        thread_id=thread_id,
        authorized_order_ids=authorized_order_ids,
        astream_generate_fn=astream_generate_with_agent_prompt,
        on_token=on_token,
    )
    return state


def _event(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "data": data}


class ChatManager:
    def __init__(self, store: ChatStore, pubsub: ChatPubSub, agent_fn: AgentFn = default_agent_fn) -> None:
        self.store = store
        self.pubsub = pubsub
        self._agent_fn = agent_fn
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._streaming_message: dict[str, ChatMessage] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def _publish(self, session_id: str, name: str, data: dict[str, Any]) -> None:
        self.pubsub.publish(channel_for(session_id), _event(name, {"session_id": session_id, **data}))

    def is_generating(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    async def submit_user_message(self, session_id: str, text: str) -> None:
        """Un `user_message` mientras el agente sigue respondiendo cuenta
        como interrupción: primero se aborta la generación en curso."""

        async with self._lock(session_id):
            await self._abort_running(session_id)
            self._start_turn(session_id, text)

    async def interrupt(self, session_id: str, new_input: str | None) -> None:
        async with self._lock(session_id):
            await self._abort_running(session_id)
            if new_input and new_input.strip():
                self._start_turn(session_id, new_input)

    async def close_session(self, session_id: str) -> None:
        async with self._lock(session_id):
            await self._abort_running(session_id)
            session = self.store.get_session(session_id)
            if session is not None:
                session.status = ChatSessionStatus.CLOSED
            self.pubsub.publish(channel_for(session_id), None)

    async def wait_idle(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)

    async def _abort_running(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is None or task.done():
            return

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        message = self._streaming_message.pop(session_id, None)
        if message is not None and message.status == "streaming":
            message.status = "interrupted"
            session = self.store.get_session(session_id)
            if session is not None:
                session.status = ChatSessionStatus.INTERRUPTED
            self._publish(
                session_id,
                "generation_interrupted",
                {"message_id": message.message_id, "status": "interrupted"},
            )

    def _start_turn(self, session_id: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        session = self.store.get_session(session_id)
        if session is None or session.status == ChatSessionStatus.CLOSED:
            return

        session.status = ChatSessionStatus.ACTIVE
        user_message = self.store.add_message(session_id, ChatMessage(role="user", text=text))
        self._publish(session_id, "user_message", {"message_id": user_message.message_id, "text": text})

        assistant_message = self.store.add_message(session_id, ChatMessage(role="assistant", status="streaming"))
        self._streaming_message[session_id] = assistant_message
        self._tasks[session_id] = asyncio.create_task(
            self._run_generation(session_id, assistant_message, text), name=f"chat-turn-{session_id}"
        )

    async def _run_generation(self, session_id: str, message: ChatMessage, question: str) -> None:
        async def on_token(token: str) -> None:
            message.sequence += 1
            message.text += token
            self._publish(
                session_id,
                "token_chunk",
                {"message_id": message.message_id, "token": token, "sequence": message.sequence},
            )

        session = self.store.get_session(session_id)
        try:
            # Auditoría OWASP A01: el ACL de pedidos sale del `user_id` de la
            # sesión (el `sub` del JWT verificado al conectar), nunca del cliente.
            state = await self._agent_fn(
                question=question,
                thread_id=session_id,
                on_token=on_token,
                authorized_order_ids=authorized_order_ids_for(session.user_id) if session else [],
            )
            final_text = state.get("answer") or state.get("error") or ""
        except asyncio.CancelledError:
            raise
        except Exception:
            # Nunca un stack trace al cliente -- mismo criterio que POST /agent/query.
            logger.exception("Fallo del agente en la sesión %s", session_id)
            final_text = FAILURE_ANSWER

        streamed = message.text
        replaced = not final_text.startswith(streamed)
        if not replaced:
            for token in split_into_tokens(final_text[len(streamed):]):
                await on_token(token)
                await asyncio.sleep(0)  # punto de cancelación entre tokens no-LLM

        message.status = "complete"
        self._streaming_message.pop(session_id, None)
        if replaced:
            # output_guard reemplazó la respuesta: el historial guarda la
            # versión segura y los clientes la reciben por snapshot.
            message.text = final_text
            self._publish(session_id, "session_snapshot", self.store.snapshot(session_id))
        self._publish(session_id, "generation_completed", {"message_id": message.message_id})
