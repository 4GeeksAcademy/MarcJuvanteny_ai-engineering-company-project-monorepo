"""Registro auditable de decisiones de memoria (`CONTEXT/CONTEXT8.md`,
"Cada decisión (propuesta, resultado, mensaje que la originó, marca de
tiempo) queda registrada de forma auditable, sin importar si la propuesta
fue aprobada o rechazada").

JSONL append-only en disco, mismo patrón que
`data/eval/agent-traces/<thread_id>.json` (Hito 7) -- consultable después
de la corrida, sin necesitar un backend de logs centralizado que este repo
no tiene. A diferencia de los traces (uno por archivo, sobreescribibles),
el audit log es un único archivo de **solo anexar** -- cada línea es un
registro inmutable, apropiado para una auditoría.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
AUDIT_LOG_PATH = ROOT_DIR / "data" / "eval" / "agent-memory-audit.jsonl"


def record_memory_decision(
    *,
    thread_id: str,
    proposal: dict[str, Any],
    outcome: str,
    triggering_message: str,
    edited_fact: str | None = None,
) -> None:
    """Un registro por decisión, sin importar si `outcome` fue `"approved"`,
    `"rejected"` o `"edited"` -- la auditoría cubre las tres, no solo las
    aprobadas."""

    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "thread_id": thread_id,
        "proposal": proposal,
        "outcome": outcome,
        "triggering_message": triggering_message,
        "edited_fact": edited_fact,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_audit_log() -> list[dict[str, Any]]:
    """Lee el log completo -- usado por tests y por cualquier revisión
    manual (`cat data/eval/agent-memory-audit.jsonl`)."""

    if not AUDIT_LOG_PATH.exists():
        return []
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
