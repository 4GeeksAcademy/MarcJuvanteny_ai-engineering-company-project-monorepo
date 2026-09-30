"""MCP Server de TrackFlow (checklist "Servidor MCP") -- expone tools reales
sobre el Incidents Manager y el inventario a cualquier agente/cliente MCP
autorizado.

## Arquitectura de autenticacion (OAuth 2.1 / OIDC via MCP Auth, RFC 9728)

Este servidor NUNCA usa la capa OAuth/auth integrada de FastMCP
(`fastmcp.server.auth`) -- el checklist la prohibe explicitamente para este
proyecto. En su lugar usa `mcpauth` (paquete Python real, ver `auth.py`) como
middleware ASGI de Starlette, montado SOLO sobre el sub-app que sirve el
endpoint MCP real (`/mcp`), no sobre el app raiz completo:

```
Starlette (app raiz, SIN auth)
├── GET /.well-known/oauth-authorization-server   (publico, RFC 8414, mcpauth.metadata_route())
├── GET /.well-known/oauth-protected-resource      (publico, RFC 9728, auth.py)
└── Mount("/") -> FastMCP.http_app(middleware=[bearer_auth])  (PROTEGIDO)
    └── POST /mcp   (requiere Authorization: Bearer <jwt> valido)
```

Los endpoints de metadata deben quedar PUBLICOS (un cliente los necesita
*antes* de tener un token, para descubrir el authorization server) -- por
eso viven en el app raiz, fuera del alcance del middleware de bearer auth,
que solo envuelve el sub-app montado. Ver `auth.py` para el porque
`mcpauth` 0.1.1 no trae Protected Resource Metadata (RFC 9728) de fabrica y
se implementa a mano ahi.

Ningun cliente sin un access token valido puede listar ni invocar tools: el
middleware de bearer auth corre para *toda* request al sub-app MCP, incluido
`tools/list` (MCP discovery) -- no solo `tools/call`.

## Scopes / minimo privilegio

Ver `scopes.py`: el middleware exige el scope base `mcp:access` (discovery);
cada tool exige ademas su propio scope especifico
(`incidents:read`/`incidents:write`/`inventory:read`) a mano, porque MCP Auth
no soporta `required_scopes` distintos por tool bajo un unico endpoint `/mcp`.

## Backend real

Las tools (`tools/incidents_tools.py`, `tools/inventory_tools.py`) llaman a
`services/incidents-api` real por HTTP -- nunca datos simulados. Ver
`backend_client.py` para las credenciales backend-a-backend (separadas del
OAuth que protege este servidor).
"""

from __future__ import annotations

import os

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.routing import Mount

import scopes
from auth import (
    MCP_SERVER_RESOURCE_URL,
    MCPAUTH_AUDIENCE,
    build_mcp_auth_from_env,
    protected_resource_metadata_route,
)
from logging_middleware import ToolInvocationLoggingMiddleware
from tools.incidents_tools import (
    CreateIncidentTicketInput,
    IncidentToolOutput,
    QueryIncidentInput,
    UpdateIncidentStatusInput,
    create_incident_ticket,
    query_incident,
    update_incident_status,
)
from tools.inventory_tools import (
    InventoryToolOutput,
    QueryInventoryInput,
    UpdateInventoryStockInput,
    query_inventory,
    update_inventory_stock,
)

mcp = FastMCP(name="trackflow-mcp")


@mcp.tool
def query_incident_tool(query: QueryIncidentInput) -> IncidentToolOutput:
    """Consulta uno o mas tickets del Incidents Manager de TrackFlow por ID
    o por filtros (status/origin/branch/category). Solo lectura. Requiere
    el scope 'incidents:read'."""

    scopes.require_scope("incidents:read")
    return query_incident(query)


@mcp.tool
def create_incident_ticket_tool(payload: CreateIncidentTicketInput) -> IncidentToolOutput:
    """Crea un ticket nuevo en el Incidents Manager de TrackFlow. Requiere el
    scope 'incidents:write'."""

    scopes.require_scope("incidents:write")
    return create_incident_ticket(payload)


@mcp.tool
def update_incident_status_tool(payload: UpdateIncidentStatusInput) -> IncidentToolOutput:
    """Actualiza el estado de un ticket existente a traves del endpoint de
    ciclo de vida real del Incidents Manager (valida transiciones: open ->
    in_progress/discarded, in_progress -> resolved/discarded; resolved y
    discarded son terminales). Requiere el scope 'incidents:write'."""

    scopes.require_scope("incidents:write")
    return update_incident_status(payload)


@mcp.tool
def query_inventory_tool(query: QueryInventoryInput) -> InventoryToolOutput:
    """Consulta el catalogo de inventario de TrackFlow, opcionalmente
    filtrado por SKU exacto. Solo lectura. Requiere el scope
    'inventory:read'."""

    scopes.require_scope("inventory:read")
    return query_inventory(query)


@mcp.tool
def update_inventory_stock_tool(payload: UpdateInventoryStockInput) -> InventoryToolOutput:
    """SIEMPRE rechaza: la tool de inventario de TrackFlow es de solo
    lectura. Existe para que un intento de modificacion reciba un rechazo
    explicito y descubrible en vez de un error generico o silencio. Requiere
    el scope 'inventory:read' (nunca existe 'inventory:write')."""

    scopes.require_scope("inventory:read")
    return update_inventory_stock(payload)


def build_app(mcp_auth=None, *, verify_mode: str | object = "jwt") -> Starlette:
    """:param mcp_auth: `MCPAuth` ya construido. Si se omite, se arma desde
    `MCPAUTH_ISSUER` (produccion). Los tests inyectan uno construido contra
    el emisor local de `tests/dev_idp.py`, sin red.
    :param verify_mode: "jwt" (default, produccion -- valida contra el JWKS
    real via HTTP) o un `VerifyAccessTokenFunction` inyectable (tests, sin
    red -- ver `mcpauth.utils.create_verify_jwt(PyJWK(...))`)."""

    if mcp_auth is None:
        mcp_auth = build_mcp_auth_from_env()
    scopes.configure(mcp_auth)

    bearer_auth = mcp_auth.bearer_auth_middleware(
        verify_mode,
        audience=MCPAUTH_AUDIENCE,
        required_scopes=[scopes.BASE_SCOPE],
    )

    mcp.add_middleware(ToolInvocationLoggingMiddleware(mcp_auth))

    mcp_app = mcp.http_app(path="/mcp", middleware=[ASGIMiddleware(bearer_auth)])

    return Starlette(
        routes=[
            mcp_auth.metadata_route(),
            protected_resource_metadata_route(MCP_SERVER_RESOURCE_URL, mcp_auth.server.metadata.issuer),
            Mount("/", app=mcp_app),
        ],
        lifespan=mcp_app.lifespan,
    )


if __name__ == "__main__":
    import uvicorn

    app = build_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("MCP_SERVER_PORT", "8010")))
