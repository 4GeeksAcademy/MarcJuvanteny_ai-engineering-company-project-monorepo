"""Observabilidad mínima de guardrails (`CONTEXT/CONTEXT8.2.md`,
"Observabilidad mínima"). Mismo patrón que `memory_audit.py` (JSONL
append-only, consultable después de la corrida) + contadores en memoria
del proceso para el resumen en vivo ("cuántas veces se activó cada
guardrail durante una sesión de pruebas" -- una sesión de pruebas vive
dentro de un proceso, por eso contadores de proceso alcanzan, no hace
falta una base de datos).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
GUARDRAIL_LOG_PATH = ROOT_DIR / "data" / "eval" / "agent-guardrail-log.jsonl"

_by_guardrail: Counter[str] = Counter()
_by_category: Counter[str] = Counter()


def record_guardrail_event(
    *,
    guardrail_name: str,
    category: str,
    action: str,
    question: str,
    thread_id: str,
) -> None:
    """Llamado cada vez que un guardrail bloquea o redirige una solicitud
    -- nunca cuando deja pasar algo sin cambios (eso no es un evento de
    guardrail, es el camino feliz)."""

    _by_guardrail[guardrail_name] += 1
    _by_category[category] += 1

    GUARDRAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "guardrail_name": guardrail_name,
        "category": category,
        "action": action,
        "question": question,
        "thread_id": thread_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with GUARDRAIL_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_summary() -> dict[str, Any]:
    """Checklist: "Expón un resumen simple (endpoint o comando) de cuántas
    veces se activó cada guardrail durante una sesión de pruebas" -- ver
    `routers/agent.py::GET /agent/guardrails/summary`."""

    return {
        "total_events": sum(_by_guardrail.values()),
        "by_guardrail": dict(_by_guardrail),
        "by_category": dict(_by_category),
    }


def reset_counters() -> None:
    """Los contadores son de proceso, no persisten entre reinicios --
    usado por tests para empezar cada uno desde cero."""

    _by_guardrail.clear()
    _by_category.clear()


def read_guardrail_log() -> list[dict[str, Any]]:
    if not GUARDRAIL_LOG_PATH.exists():
        return []
    lines = GUARDRAIL_LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
