"""Checklist: "Registrar en logs cada invocacion de tool (que tool, que
cliente, que resultado) para trazabilidad."

Middleware de FastMCP real (`fastmcp.server.middleware.Middleware`, hook
`on_call_tool`) -- se engancha al despacho `tools/call` del protocolo MCP en
si (no al transporte HTTP), asi que registra toda invocacion sin importar el
transporte. El "cliente" se identifica por `client_id`/`subject` del
`AuthInfo` que `mcpauth` ya valido para este request (nunca se confia en un
campo que el propio payload de la tool pueda declarar).
"""

from __future__ import annotations

import logging

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from mcpauth import MCPAuth

logger = logging.getLogger("trackflow_mcp.tool_invocations")


class ToolInvocationLoggingMiddleware(Middleware):
    def __init__(self, mcp_auth: MCPAuth):
        self._mcp_auth = mcp_auth

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext):
        tool_name = getattr(context.message, "name", "<unknown_tool>")
        auth_info = self._mcp_auth.auth_info
        client_id = (auth_info.client_id or auth_info.subject) if auth_info else "<unauthenticated>"

        try:
            result = await call_next(context)
        except Exception as exc:
            logger.info("tool=%s client=%s result=error detail=%s", tool_name, client_id, exc)
            raise

        logger.info("tool=%s client=%s result=ok", tool_name, client_id)
        return result
