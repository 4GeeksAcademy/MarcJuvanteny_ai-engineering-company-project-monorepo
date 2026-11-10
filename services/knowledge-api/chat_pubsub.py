"""Pub/sub en memoria del chat por WebSocket (`CONTEXT/CONTEXT10.md`, Parte 2,
§5 "Patrón Pub/Sub"): un canal por sesión, `chat.<session_id>`.

- **Productor**: la tarea que corre un turno del agente
  (`chat_runner.py::ChatManager`) publica `token_chunk`,
  `generation_interrupted`, `generation_completed`, ... en el canal de su
  sesión. Nunca conoce ni toca un WebSocket.
- **Consumidores**: cada conexión WebSocket (`routers/chat.py`) se suscribe
  al canal de su sesión y reenvía lo que llega. Pueden ser 0 (el cliente se
  cayó: el agente sigue generando y el texto queda en el historial), 1, o
  varias pestañas a la vez.

En memoria (una `asyncio.Queue` por suscriptor): CONTEXT10.md lo acepta
"si tu implementación corre en un solo proceso", y este servicio corre así
(`uvicorn main:app`, un worker). Para varios workers, la misma interfaz
`publish`/`subscribe` se respalda con Redis pub/sub sin tocar productor ni
consumidores.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


def channel_for(session_id: str) -> str:
    return f"chat.{session_id}"


class ChatPubSub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any] | None]]] = defaultdict(set)

    def subscribe(self, channel: str) -> asyncio.Queue[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._subscribers[channel].add(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        subscribers = self._subscribers.get(channel)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(channel, None)

    def publish(self, channel: str, event: dict[str, Any] | None) -> int:
        """`None` es la señal de "cerrar" para los consumidores (sesión
        cerrada). Devuelve cuántos suscriptores lo recibieron."""

        subscribers = list(self._subscribers.get(channel, ()))
        for queue in subscribers:
            queue.put_nowait(event)
        return len(subscribers)

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, ()))
