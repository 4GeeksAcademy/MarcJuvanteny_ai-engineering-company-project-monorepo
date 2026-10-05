"""`POST /agent/query` (CONTEXT7.md, sección "Endpoint").

Convive con `POST /knowledge/query` (Fase 3 del RAG) en el mismo servicio —
no lo reemplaza. Capa HTTP fina: solo invoca al grafo compilado
(`agent_graph.run_agent()`), sin lógica de negocio propia (ni recuperación
ni generación ni enrutamiento viven acá, eso es responsabilidad del grafo).

`payload.thread_id` se reenvía a `run_agent()` y se devuelve siempre en la
respuesta (Hito 8 Parte 1, memoria): es lo que le permite a un cliente
retomar la conversación en el turno siguiente para resolver una propuesta
de memoria pendiente -- ver `schemas.py::AgentQueryResponse`.

`GET /agent/guardrails/summary` (Hito 8 Parte 2, "Observabilidad mínima"):
expone cuántas veces se activó cada guardrail durante la sesión de pruebas
actual (contadores de proceso, ver `guardrail_audit.py`).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from schemas import AgentQueryResponse, QueryRequest

from agent_graph import run_agent
from guardrail_audit import get_summary

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger("agent")


@router.post("/query", response_model=AgentQueryResponse)
async def query_agent(payload: QueryRequest) -> AgentQueryResponse:
    try:
        state, _trace, thread_id = await run_agent(
            payload.question, thread_id=payload.thread_id, authorized_order_ids=payload.authorized_order_ids
        )
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

    if state.get("guardrail_blocked"):
        logger.info("agent thread_id=%s -- bloqueada por un guardrail", thread_id)
    else:
        logger.info("agent thread_id=%s -- trace consultable en data/eval/agent-traces/%s.json", thread_id, thread_id)

    return AgentQueryResponse(answer=state.get("answer") or "", thread_id=thread_id)


@router.get("/guardrails/summary")
async def guardrails_summary() -> dict[str, Any]:
    return get_summary()
