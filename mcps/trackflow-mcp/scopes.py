"""Minimo privilegio por-tool (checklist: "cada tool solo tiene acceso a los
datos y operaciones que necesita para cumplir su funcion").

MCP Auth (`bearer_auth_middleware(required_scopes=[...])`) solo admite UN
`required_scopes` global para todo el ASGI app que protege -- y este server
expone todas sus tools bajo un unico endpoint MCP (`/mcp`, JSON-RPC
`tools/call`), asi que no hay forma de aplicar un `required_scopes` distinto
por tool a nivel de middleware/ruta HTTP (ver `server.py`). Por eso el
middleware exige solo el scope base `mcp:access` (cualquier cliente
autenticado puede *listar* tools -- discovery, ver checklist de
documentacion), y cada tool verifica su propio scope especifico aca, a mano,
contra el `AuthInfo` que `mcpauth` ya valido (firma, issuer, audiencia).

Scopes definidos (ver `Pasos/mcp-server-tools.md`):
- `incidents:read`  -- consultar tickets (`query_incident`).
- `incidents:write` -- crear/actualizar tickets (`create_incident_ticket`,
  `update_incident_status`).
- `inventory:read`  -- consultar inventario (`query_inventory`). No existe
  `inventory:write`: la tool de inventario es de solo lectura por diseno
  (ver `tools/inventory_tools.py`).

Codigo de error documentado: una tool sin el scope requerido levanta
`ScopeError`, que FastMCP convierte en un `CallToolResult(isError=True)`
para el cliente MCP con mensaje `missing_required_scope: ...` -- nunca un
"error" generico ni una respuesta silenciosamente vacia.
"""

from __future__ import annotations

from mcpauth import MCPAuth

BASE_SCOPE = "mcp:access"

_mcp_auth: MCPAuth | None = None


class ScopeError(Exception):
    """Levantada por una tool cuando el token autenticado no trae el scope
    que esa tool especifica requiere. Codigo documentado:
    `missing_required_scope`."""

    def __init__(self, required_scope: str, actual_scopes: list[str]):
        self.code = "missing_required_scope"
        self.required_scope = required_scope
        self.actual_scopes = actual_scopes
        super().__init__(
            f"missing_required_scope: esta operacion requiere el scope '{required_scope}' "
            f"(el token presentado tiene: {actual_scopes or 'ninguno'})."
        )


def configure(mcp_auth: MCPAuth) -> None:
    """Llamado una vez desde `server.py` al construir el `MCPAuth` real (o el
    de pruebas) -- las tools leen `mcp_auth.auth_info` a traves de aca en vez
    de importar `server.py` directamente, para evitar un import circular
    (`server.py` registra las tools, las tools necesitan el auth ya armado)."""

    global _mcp_auth
    _mcp_auth = mcp_auth


def require_scope(scope: str) -> None:
    """:raises RuntimeError: si `configure()` todavia no corrio (bug de
    arranque del servidor, no un caso de negocio).
    :raises ScopeError: si no hay `AuthInfo` en contexto o el scope falta.
    """

    if _mcp_auth is None:
        raise RuntimeError("scopes.configure() no fue llamado -- el MCP Server no inicializo MCP Auth todavia.")

    auth_info = _mcp_auth.auth_info
    actual_scopes = list(auth_info.scopes) if auth_info else []
    if auth_info is None or scope not in actual_scopes:
        raise ScopeError(scope, actual_scopes)
