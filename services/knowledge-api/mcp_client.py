"""Cliente MCP del agente hacia `mcps/trackflow-mcp` (checklist "Migración
del agente"): el agente ya no llama directamente a `services/incidents-api`
-- pasa siempre por el MCP Server, vía `langchain-mcp-adapters` (el adapter
oficial de LangChain/MCP, paquete real `langchain-mcp-adapters` de PyPI).
Reemplaza `tools/incidents_tool.py`/`tools/inventory_tool.py` (HTTP directo
al Incidents Manager, eliminados -- ver `Pasos/rag-knowledge-base-fase1.md`)
para que el agente tenga un único camino posible hacia el Incidents Manager:
el MCP Server.

## Por qué un `ToolCall` y no argumentos planos en `ainvoke()`

`BaseTool.ainvoke(dict_de_argumentos)` devuelve solo el `content` (texto) de
la respuesta MCP -- para tools que devuelven un modelo Pydantic (como las de
`mcps/trackflow-mcp`), eso es el JSON *serializado como texto*, no un dict.
`BaseTool.ainvoke(tool_call)` (el formato `ToolCall` de LangChain: `{"name",
"args", "id", "type": "tool_call"}`) devuelve en cambio un `ToolMessage`
completo, cuyo `.artifact["structured_content"]` **ya es el dict real** --
el mismo shape que `structuredContent` del protocolo MCP (ver
`server.py`/`tools/*.py` de `mcps/trackflow-mcp`). Confirmado
empíricamente antes de escribir este código (no asumido): un `ToolMessage`
exitoso trae `status="ok"` y ese `artifact`; uno fallido (p. ej.
`ScopeError` del MCP Server) trae `status="error"`, `artifact=None`, y el
mensaje de error como texto en `.content[0]["text"]`.

## Token del agente hacia el MCP Server

Backend-a-backend, igual que `INCIDENTS_API_TOKEN` en la implementación
anterior: se lee de `MCP_SERVER_TOKEN` (entorno/`.env`), nunca hardcodeado.
En producción, ese token saldría de un flujo OAuth 2.1 client-credentials
real contra el `MCPAUTH_ISSUER` del MCP Server (renovado periódicamente) --
no implementado en este repo porque no hay un proveedor OIDC real
configurado (mismo límite documentado en `mcps/trackflow-mcp/auth.py`); acá
se asume un token ya emitido y vigente, leído de entorno como cualquier otra
credencial backend-a-backend de este monorepo.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8010/mcp")
MCP_SERVER_TOKEN = os.environ.get("MCP_SERVER_TOKEN", "")
# Valor concreto, no "razonable": la llamada implica un handshake MCP
# (tools/list o tools/call) además del tiempo del propio backend de
# incidents-api -- un poco mas generoso que el timeout HTTP directo que
# reemplaza (antes 4s), pero sigue siendo corto y explícito.
MCP_TIMEOUT_SECONDS = float(os.environ.get("MCP_TIMEOUT_SECONDS", "8"))


def _auth_headers() -> dict[str, str]:
    if not MCP_SERVER_TOKEN:
        return {}
    return {"Authorization": f"Bearer {MCP_SERVER_TOKEN}"}


def build_mcp_client(
    *,
    url: str = MCP_SERVER_URL,
    token: str = MCP_SERVER_TOKEN,
    timeout: float = MCP_TIMEOUT_SECONDS,
) -> MultiServerMCPClient:
    """Cliente nuevo por llamada -- mismo patrón que `httpx.Client()` fresco
    en cada llamada de las tools HTTP directas que este módulo reemplaza."""

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return MultiServerMCPClient(
        {
            "trackflow": {
                "transport": "streamable_http",
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        }
    )


async def call_mcp_tool(
    tool_name: str,
    args: dict[str, Any],
    *,
    client_factory=build_mcp_client,
) -> dict[str, Any]:
    """Invoca una tool del MCP Server y devuelve su `structured_content`
    como dict plano -- mismo contrato de salida (`ok`/`error`/...) que las
    tools HTTP directas que reemplaza, para no tener que tocar
    `_tool_result_to_context_chunks()` en `agent_graph.py`.

    Nunca deja una excepción cruda escapar hacia el grafo: una falla de
    conexión/timeout hacia el MCP Server (el servidor no está corriendo, la
    red falla) se traduce en `{"ok": False, "error": "connection_error:..."}`,
    igual que antes con `httpx.RequestError`. Un error a nivel de tool (p. ej.
    scope faltante) se traduce en `{"ok": False, "error": "<mensaje>"}` a
    partir del `ToolMessage(status="error")` que MCP Auth ya documenta (ver
    `mcps/trackflow-mcp/scopes.py`).
    """

    try:
        client = client_factory()
        tools = await client.get_tools()
    except Exception as exc:  # conexión/timeout/handshake MCP -- nunca deja el grafo colgado
        return {"ok": False, "error": f"connection_error:{exc}"}

    tool_by_name = {tool.name: tool for tool in tools}
    tool = tool_by_name.get(tool_name)
    if tool is None:
        return {"ok": False, "error": f"tool_not_found:{tool_name}"}

    tool_call = {"name": tool_name, "args": args, "id": str(uuid.uuid4()), "type": "tool_call"}
    try:
        result = await tool.ainvoke(tool_call)
    except Exception as exc:
        return {"ok": False, "error": f"connection_error:{exc}"}

    if result.status == "error":
        message = result.content[0]["text"] if result.content else "error desconocido"
        return {"ok": False, "error": message}

    return dict(result.artifact["structured_content"])
