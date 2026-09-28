"""Config compartida por las tools del agente que llaman al backend real de
TrackFlow (`services/incidents-api/` — sirve tanto `/api/incidents` como
`/inventory/products`, es el mismo proceso/servicio, ver `routers/inventory.py`
registrado en su `main.py`). Una sola URL/timeout/token para ambas tools.

Backend-a-backend: si `INCIDENTS_API_TOKEN` está configurado, se manda como
`Authorization: Bearer ...` en cada llamada — nunca hardcodeado, siempre
leído de entorno/config (`.env`). `services/incidents-api` sí requiere auth
en `GET /api/incidents*` (`Depends(get_current_user)`) — no en
`GET /inventory/products`, pero se manda el header en ambos casos por
simplicidad, es inofensivo cuando no hace falta.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVICE_DIR / ".env")

INCIDENTS_API_URL = os.environ.get("INCIDENTS_API_URL", "http://localhost:8001")
INCIDENTS_API_TOKEN = os.environ.get("INCIDENTS_API_TOKEN", "")
# Valor concreto (no "un timeout razonable"): 4s. Justificacion: las tools
# son consultas de solo lectura sobre TinyDB/SQL, tipicamente responden en
# milisegundos -- 4s ya es un margen generoso para un backend saludable, y
# corto para no dejar el grafo colgado si el backend esta caido/degradado.
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("INCIDENTS_API_TIMEOUT_SECONDS", "4"))


def auth_headers() -> dict[str, str]:
    if not INCIDENTS_API_TOKEN:
        return {}
    return {"Authorization": f"Bearer {INCIDENTS_API_TOKEN}"}
