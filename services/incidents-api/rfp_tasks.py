"""Tarea Celery del flujo de recepción de RFPs (`CONTEXT/CONTEXT9.md`,
"Interfaz de recepción (modo ticket)": "el endpoint de subida responde
rápido; el pipeline corre en async"). Mismo mecanismo que
`tasks.py::analyze_incidents_csv_task` (Redis como broker, ver
`celery_app.py`) -- un proceso de worker independiente, nunca el proceso
de FastAPI, corre `process_rfp_ticket()`.

A diferencia de `analyze_incidents_csv_task`, esta tarea no le devuelve el
resultado al cliente vía `GET /tasks/{task_id}` -- el estado real vive en
`RFPTicket.status` (Postgres), que es lo que `GET /rfp/tickets/{id}`
consulta. El `task_id` de Celery no importa para el flujo de negocio, solo
para observabilidad/logs.
"""

from __future__ import annotations

import rfp_pipeline_path  # noqa: F401

from celery_app import celery_app
from rfp_intake.pipeline import process_rfp_ticket


@celery_app.task(name="rfp_tasks.process_rfp_ticket_task")
def process_rfp_ticket_task(ticket_id: int) -> dict:
    return process_rfp_ticket(ticket_id)
