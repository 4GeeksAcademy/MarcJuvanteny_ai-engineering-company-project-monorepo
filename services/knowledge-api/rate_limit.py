"""Rate limiting de las llamadas al modelo (Hito 12, seguridad por diseño --
`Pasos/nist-seguridad-ia.md`).

Antes no había ninguno: un cliente (o un bucle de reconexión, o alguien
mandando `interrupt_requested` con `new_input` en cada tick) podía disparar
turnos del agente sin tope -- cada turno es una llamada al LLM de un
proveedor externo que se paga por token.

Un único presupuesto POR USUARIO compartido entre todos los caminos que
llaman al modelo: `POST /agent/query`, `POST /knowledge/query` y cada turno
nuevo del chat por WebSocket (`user_message` o `interrupt_requested` con
`new_input`). Detener una generación (`interrupt_requested` sin
`new_input`) no consume: reduce coste, no lo aumenta.

En memoria y por proceso, igual que `chat_pubsub.py`: este servicio corre
con un solo worker. Con varios, la misma interfaz se respalda con Redis
(`INCR` + `EXPIRE`).
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic

from fastapi import HTTPException, status


def _limit_from_env() -> int:
    """`0` es válido a propósito: corta TODAS las llamadas al modelo (palanca
    de contención del plan de respuesta, Pasos/nist-seguridad-ia.md §6 RS)."""

    try:
        return max(0, int(os.environ.get("AGENT_RATE_LIMIT_PER_MINUTE", "20")))
    except ValueError:
        return 20


class SlidingWindowRateLimiter:
    def __init__(self, max_calls: int, window_seconds: float = 60.0, clock: Callable[[], float] = monotonic) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._clock = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def try_acquire(self, key: str) -> float | None:
        """Registra la llamada y devuelve `None` si está dentro del límite;
        si no, NO la registra y devuelve los segundos hasta que se libere un
        cupo (para `Retry-After`)."""

        if self.max_calls <= 0:
            return self.window_seconds
        now = self._clock()
        with self._lock:
            calls = self._calls[key]
            while calls and now - calls[0] >= self.window_seconds:
                calls.popleft()
            if len(calls) >= self.max_calls:
                return max(0.0, self.window_seconds - (now - calls[0]))
            calls.append(now)
            return None


_MODEL_CALL_LIMITER = SlidingWindowRateLimiter(_limit_from_env())


def get_model_rate_limiter() -> SlidingWindowRateLimiter:
    return _MODEL_CALL_LIMITER


RATE_LIMITED_MESSAGE = "Demasiadas consultas seguidas. Espera unos segundos e inténtalo de nuevo."


def enforce_model_rate_limit(limiter: SlidingWindowRateLimiter, user_id: str) -> None:
    retry_after = limiter.try_acquire(user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMITED_MESSAGE,
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )
