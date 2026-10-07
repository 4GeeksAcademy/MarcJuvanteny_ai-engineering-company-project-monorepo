# trackflow-mcp

MCP Server de TrackFlow. Expone tools reales sobre el Incidents Manager
(`services/incidents-api`) y el inventario a cualquier agente/cliente MCP
autorizado, protegido con OAuth 2.1 / OIDC via [MCP Auth](https://mcp-auth.dev)
(nunca la capa de auth integrada de FastMCP).

Documentacion completa de la implementacion, decisiones y verificacion:
[`Pasos/mcp-server-tools.md`](../../Pasos/mcp-server-tools.md).

## Tools expuestas

| Tool | Scope requerido | Que hace |
|---|---|---|
| `query_incident_tool` | `incidents:read` | Consulta uno o mas tickets por ID o filtros. Solo lectura. |
| `create_incident_ticket_tool` | `incidents:write` | Crea un ticket nuevo. |
| `update_incident_status_tool` | `incidents:write` | Actualiza el estado de un ticket via el endpoint de ciclo de vida real (`PATCH /api/incidents/{id}/status`). |
| `query_inventory_tool` | `inventory:read` | Consulta el catalogo de inventario, opcionalmente por SKU. Solo lectura. |
| `update_inventory_stock_tool` | `inventory:read` | Rechaza SIEMPRE explicitamente (la tool de inventario nunca escribe). |

## Correr localmente

```bash
uv sync
cp .env.example .env   # completar INCIDENTS_API_URL, MCPAUTH_ISSUER, etc.
uv run python server.py
```

Sin un `MCPAUTH_ISSUER` real (OAuth 2.1 / OIDC), el servidor no arranca --
ver `auth.py`.

## Tests

```bash
uv run pytest tests/
```

No requieren red ni un proveedor OIDC real: `tests/dev_idp.py` firma JWTs
RS256 reales con una clave generada en memoria para los tests (ver su
docstring y `Pasos/mcp-server-tools.md`).
