"""Registro de decisiones del agente CX: qué acción tomó cada nodo y POR QUÉ
(Hito 12, seguridad por diseño -- `Pasos/nist-seguridad-ia.md`).

Diferencia con el trace que ya existía (`agent_graph._save_trace`,
`data/eval/agent-traces/<thread_id>.json`): ese guarda el estado crudo de
cada nodo, incluidos la pregunta y la respuesta completas (datos del
destinatario: RGPD art. 5 minimización / CCPA), y no dice el motivo de cada
decisión. Este registro es el de auditoría:

- una línea JSON por paso: `node`, `action`, `reason`;
- quién (`actor_id`, el `sub` del JWT) y en qué hilo (`thread_id` = `session_id`);
- la pregunta NUNCA en claro: solo su longitud y un hash corto (para
  correlacionar con una queja sin guardar el texto);
- también los turnos abortados por una interrupción (`action="cancelled"`).

Append-only, JSONL, ruta configurable con `AGENT_DECISION_LOG_PATH`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent_decisions")

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "eval" / "agent-decision-log.jsonl"
_WRITE_LOCK = threading.Lock()


def decision_log_path() -> Path:
    raw = os.environ.get("AGENT_DECISION_LOG_PATH")
    return Path(raw) if raw else _DEFAULT_PATH


def question_fingerprint(question: str) -> dict[str, Any]:
    return {
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()[:16],
        "question_chars": len(question),
    }


def write_decisions(
    *, thread_id: str, actor_id: str | None, question: str, steps: list[dict[str, str]]
) -> None:
    """Nunca rompe un turno del agente: si el disco falla, se avisa por log
    y la respuesta al cliente sigue su curso."""

    timestamp = datetime.now(timezone.utc).isoformat()
    base = {"ts": timestamp, "thread_id": thread_id, "actor_id": actor_id, **question_fingerprint(question)}
    lines = [json.dumps({**base, "step": index, **step}, ensure_ascii=False) for index, step in enumerate(steps)]
    path = decision_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        logger.exception("No se pudo escribir el registro de decisiones del agente en %s", path)
