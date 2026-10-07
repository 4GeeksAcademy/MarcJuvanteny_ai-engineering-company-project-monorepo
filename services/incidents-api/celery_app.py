"""Instancia de Celery: Redis como broker y como result backend.

El worker corre como proceso independiente (`celery -A celery_app worker`,
ver `docker-compose.yml` -> servicio `worker`), nunca dentro del proceso de
FastAPI (`main.py` solo encola tareas con `.delay()` y consulta su estado via
`AsyncResult`; nunca importa ni ejecuta la logica de `tasks.py` en el hilo de
un request).
"""

from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


celery_app = Celery(
    "incidents_api",
    broker=_redis_url(),
    backend=_redis_url(),
    include=["tasks"],
)

celery_app.conf.update(
    # Sin esto Celery nunca reporta el estado STARTED (salta directo de
    # PENDING a SUCCESS/FAILURE) -- GET /tasks/{task_id} necesita distinguir
    # "en cola" de "corriendo".
    task_track_started=True,
    # 24h: tiempo suficiente para que quien subio el CSV vuelva a consultar
    # GET /tasks/{task_id} sin que el resultado ya haya expirado de Redis.
    result_expires=60 * 60 * 24,
    # Si el proceso de Celery arranca antes de que Redis este listo (caso
    # tipico en docker-compose: "worker" y "redis" arrancan casi a la vez),
    # reintenta la conexion en vez de morir al primer intento.
    broker_connection_retry_on_startup=True,
    # ack tardio: si el worker muere a mitad de la tarea, el mensaje vuelve
    # a la cola en vez de perderse (complementa maxmemory-policy=noeviction
    # en Redis: ni el broker descarta el mensaje bajo presion de memoria, ni
    # el worker lo da por hecho antes de terminar).
    task_acks_late=True,
)
