"""`POST /agent/query` (CONTEXT7.md, sección "Endpoint").

Convive con `POST /knowledge/query` (Fase 3 del RAG) en el mismo servicio —
no lo reemplaza. Capa HTTP fina: solo invoca al grafo compilado
(`agent_graph.run_agent()`), sin lógica de negocio propia (ni recuperación
ni generación ni enrutamiento viven acá, eso es responsabilidad del grafo).

`payload.thread_id` se reenvía a `run_agent()` y se devuelve siempre en la
respuesta (Hito 8, memoria): es lo que le permite a un cliente retomar la
conversación en el turno siguiente para resolver una propuesta de memoria
pendiente -- ver `schemas.py::AgentQueryResponse`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from schemas import AgentQueryResponse, QueryRequest

from agent_graph import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger("agent")


@router.post("/query", response_model=AgentQueryResponse)
async def query_agent(payload: QueryRequest) -> AgentQueryResponse:
    try:
        state, _trace, thread_id = await run_agent(payload.question, thread_id=payload.thread_id)
    except Exception:
        # Nunca un stack trace crudo al cliente -- el detalle completo va al
        # log del servidor.
        logger.exception("Fallo al ejecutar el grafo del agente: %s", payload.question)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo generar una respuesta en este momento."
        )

    if state.get("error"):
        # Ruta de "pregunta vacia" del grafo (empty_question): no es un
        # fallo del sistema, es una respuesta explicita del enrutamiento.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=state["error"])

    logger.info("agent thread_id=%s -- trace consultable en data/eval/agent-traces/%s.json", thread_id, thread_id)
    return AgentQueryResponse(answer=state.get("answer") or "", thread_id=thread_id)
