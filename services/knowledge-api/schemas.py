from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    # Hito 8 (memoria, solo relevante para /agent/query): si se omite, el
    # agente arranca un hilo nuevo -- el cliente debe reenviar el
    # `thread_id` de AgentQueryResponse en el siguiente request para que
    # una propuesta de memoria pendiente
    # (agent_graph.py::pending_memory_proposal) pueda resolverse en el
    # turno siguiente. Sin esto, cada request era un hilo nuevo y
    # `resolve_pending_memory_proposal` nunca podía alcanzarse via HTTP.
    # Ignorado por /knowledge/query (sin concepto de hilo/conversación).
    thread_id: str | None = None
    # Hito 8 Parte 2 (guardrails, solo relevante para /agent/query): los
    # numeros de pedido/tracking que la sesion que llama puede consultar
    # legitimamente -- ver guardrails.py::check_unauthorized_tracking_request
    # y Pasos/agent-guardrails.md "Decisiones" sobre el limite real de no
    # tener un sistema de autenticacion de sesion conectado a este endpoint
    # todavia. `None` (el default) desactiva ese guardrail especifico.
    authorized_order_ids: list[str] | None = None


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


class AgentQueryResponse(BaseModel):
    """Solo para `POST /agent/query` -- `QueryResponse` no trae `thread_id`
    porque `/knowledge/query` (Fase 3) es intencionalmente sin estado, sin
    concepto de hilo/conversación; forzarle un `thread_id` sería incoherente
    con su propio diseño."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    thread_id: str
