"""Tarea Celery que encapsula la operacion pesada de `POST /api/incidents/analyze`
(la de coste "Muy alto" en `Pasos/analisis-endpoints-fastapi-coste-frecuencia.md`
seccion 3: parsear + validar + agregar un CSV completo, O(n) filas).

El endpoint ahora solo hace las validaciones baratas y sincronas (extension,
no vacio, decodificable como UTF-8) y encola esta tarea; todo el trabajo
O(n) -- `read_csv_text` (parseo + validacion estructural fila a fila) y
`summarize_rows` (agregacion) -- corre aqui, en el worker, fuera del
request/response de FastAPI.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from celery import Task

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from incident_analysis import CSVInputError, read_csv_text, summarize_rows  # noqa: E402

from celery_app import celery_app  # noqa: E402
from task_dlq import record_dlq_entry  # noqa: E402

# Backoff exponencial creciente entre reintentos: 2s, 4s, 8s
# (_RETRY_BASE_SECONDS ** intento).
_RETRY_BASE_SECONDS = 2


class AnalyzeCSVTask(Task):
    """`on_failure` es el gancho de la Dead Letter Queue: se dispara tanto
    cuando se agotan los `max_retries` (Celery lo envuelve en
    `MaxRetriesExceededError`) como cuando la tarea falla en firme sin
    reintentar (CSV mal formado, ver mas abajo) -- en ambos casos el fallo es
    definitivo y debe quedar registrado.
    """

    def on_failure(self, exc: BaseException, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], einfo: Any) -> None:
        attempt = self.request.retries + 1
        record_dlq_entry(task_id=task_id, attempt=attempt, error=str(exc))


@celery_app.task(bind=True, base=AnalyzeCSVTask, max_retries=3, name="tasks.analyze_incidents_csv")
def analyze_incidents_csv_task(self: Task, csv_text: str) -> dict[str, Any]:
    try:
        rows = read_csv_text(csv_text)
    except CSVInputError:
        # Error deterministico de formato (columnas faltantes, fila
        # malformada, etc.): el mismo CSV vuelve a fallar exactamente igual
        # en cada reintento, asi que reintentar es puro desperdicio -- falla
        # en firme de una (on_failure la manda a la DLQ igual).
        raise

    try:
        return summarize_rows(rows)
    except Exception as exc:
        countdown = _RETRY_BASE_SECONDS ** (self.request.retries + 1)
        raise self.retry(exc=exc, countdown=countdown)
