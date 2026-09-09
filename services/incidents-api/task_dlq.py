"""Dead Letter Queue de tareas Celery: `task_id`, intento, error y timestamp
de toda tarea que termino en fallo definitivo (reintentos agotados, o un
error no reintentable que fallo directo -- ver `tasks.py`).

Misma base TinyDB (`suppliers.json`) que ya usan `suppliers`/`incidents`/
`users` en este servicio (tabla nueva `task_dlq`), no una base separada: es
bookkeeping ligero y propio de `incidents-api`, mismo criterio que el resto
de tablas de esa base.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tinydb import TinyDB

from database import get_tinydb_path


def record_dlq_entry(task_id: str, attempt: int, error: str) -> None:
    with TinyDB(get_tinydb_path()) as db:
        table = db.table("task_dlq")
        table.insert(
            {
                "task_id": task_id,
                "attempt": attempt,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
