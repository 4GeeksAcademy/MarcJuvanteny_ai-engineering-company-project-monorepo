"""`POST /knowledge/query` (CONTEXT7.md, Fase 3).

Capa HTTP fina: valida el body, llama a `query()` de `data/pipelines/rag.py`
(Fase 2) y serializa la respuesta. Ninguna lógica de recuperación/generación
vive acá — si hiciera falta un cálculo nuevo, va en `data/pipelines/rag.py`,
no en este router (mismo criterio que `services/reporting/routers/reporting.py`).
"""

from __future__ import annotations

import logging

import pipeline_path  # noqa: F401  (efecto secundario: agrega data/pipelines/ a sys.path)
from fastapi import APIRouter, HTTPException, status
from schemas import QueryRequest, QueryResponse

from rag import query as rag_query

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger("knowledge")


@router.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="question no puede estar vacía.")

    try:
        answer = rag_query(question)
    except Exception as exc:
        # Detalle completo solo al log del servidor -- nunca al cliente
        # (podria filtrar detalles de la conexion a Qdrant o al LLM).
        logger.exception("Fallo al resolver la consulta de conocimiento: %s", question)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo generar una respuesta en este momento.") from exc

    return QueryResponse(answer=answer)
