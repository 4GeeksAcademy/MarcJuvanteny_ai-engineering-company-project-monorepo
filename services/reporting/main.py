"""`services/reporting/` — FastAPI app (Fase 5.1 del diseno).

App independiente, sibling de `services/incidents-api/`. Capa HTTP fina: no
importa nada de `services/incidents-api/telemetry/`, no lee `telemetry_events`
y no calcula KPIs — solo expone `reporting.*` via `data/pipelines/`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.reporting import router as reporting_router

app = FastAPI(title="Reporting API", version="0.1.0")

# Mismos origenes que services/incidents-api/main.py: el dashboard ejecutivo
# (Parte 3) vive en el mismo frontend (backoffice, puerto 3001).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(reporting_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
