"""`services/knowledge-api/` — FastAPI app (CONTEXT7.md, Fase 3 + "Grafo del agente").

App independiente, sibling de `services/incidents-api/` y
`services/reporting/`. Capa HTTP fina: no calcula embeddings, no habla con
Qdrant ni con el LLM directamente — todo eso vive en `data/pipelines/rag.py`
(Fase 2), `data/process/rag.py` (Fase 1) y `agent_graph.py` (grafo del
agente). `POST /agent/query` convive con `POST /knowledge/query` (no lo
reemplaza) en el mismo servicio.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.agent import router as agent_router
from routers.knowledge import router as knowledge_router

app = FastAPI(title="Knowledge API", version="0.1.0")

# Mismos origenes que services/reporting/main.py: el backoffice (Parte 4,
# uis/backoffice) es el consumidor de este servicio.
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

app.include_router(knowledge_router)
app.include_router(agent_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
