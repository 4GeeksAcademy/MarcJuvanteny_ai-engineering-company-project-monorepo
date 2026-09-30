"""Config compartida por las tools del MCP Server que llaman al backend real
de TrackFlow (`services/incidents-api/` -- sirve tanto `/api/incidents` como
`/inventory/products`, es el mismo proceso/servicio). Mismo patron que
`services/knowledge-api/tools/backend_client.py` (agent RAG), reutilizado
aqui porque el MCP Server llama al mismo backend por el mismo motivo: son
procesos/paquetes separados en este monorepo.

Backend-a-backend: si `INCIDENTS_API_TOKEN` esta configurado, se manda como
`Authorization: Bearer ...` en cada llamada -- nunca hardcodeado, siempre
leido de entorno/config (`.env`). Esto es DISTINTO del OAuth de `auth.py`
(ese protege el MCP Server frente a sus *clientes*; este token es el que el
MCP Server usa como *cliente* del backend de incidentes).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")

INCIDENTS_API_URL = os.environ.get("INCIDENTS_API_URL", "http://localhost:8001")
INCIDENTS_API_TOKEN = os.environ.get("INCIDENTS_API_TOKEN", "")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("INCIDENTS_API_TIMEOUT_SECONDS", "5"))


def auth_headers() -> dict[str, str]:
    if not INCIDENTS_API_TOKEN:
        return {}
    return {"Authorization": f"Bearer {INCIDENTS_API_TOKEN}"}
