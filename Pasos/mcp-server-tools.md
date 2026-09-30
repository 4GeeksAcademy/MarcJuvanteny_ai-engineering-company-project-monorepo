# MCP Server de TrackFlow — tools, OAuth, validación y migración del agente

Fecha: 2026-09-30 (Servidor MCP + Autenticación) — actualizado 2026-09-30
(Validación en MCP Playground + Migración del agente)

Implementación del checklist "Servidor MCP" / "Autenticación y seguridad":
un MCP Server en Python (`mcps/trackflow-mcp/`, via FastMCP) que expone
tools reales sobre `services/incidents-api` (gestión de tickets: crear,
actualizar estado, consultar; e inventario, solo consulta), protegido con
OAuth 2.1 / OIDC via **MCP Auth** (`mcpauth`) — nunca la capa de
autenticación integrada de FastMCP, que el checklist prohíbe explícitamente
para este proyecto. Extendido con la validación manual del servidor (MCP
Playground, vía el puerto de Codespaces reenviado públicamente) y la
migración del agente RAG (`services/knowledge-api/agent_graph.py`) para que
consuma estas mismas tools a través del MCP Server, vía
`langchain-mcp-adapters`, en vez de llamar directo a `services/incidents-api`
— la implementación HTTP directa anterior (`tools/incidents_tool.py`,
`tools/inventory_tool.py`) se eliminó.

Antes de implementar, confirmé con el desarrollador el permiso explícito
para modificar `mcps/` (ruta restringida por `AGENTS.md` sección 3) — la
carpeta solo tenía sus dos `README` de plantilla, sin ningún servidor
todavía.

## Dónde vive el código

```
mcps/trackflow-mcp/
  server.py              # FastMCP + Starlette: wiring de OAuth, tools, metadata endpoints
  auth.py                # Config de MCP Auth (AuthServerConfig real, RFC 9728 a mano)
  scopes.py               # Mínimo privilegio por-tool (ver "Decisiones" más abajo)
  backend_client.py       # Config compartida hacia services/incidents-api (mismo patrón
                           # que services/knowledge-api/tools/backend_client.py)
  logging_middleware.py   # Trazabilidad: tool + cliente + resultado en cada invocación
  dev_idp_server.py       # Emisor OAuth 2.1/OIDC de DESARROLLO real (proceso HTTP, no solo en tests) -- ver "Validación"
  tools/
    incidents_tools.py    # query_incident, create_incident_ticket, update_incident_status
    inventory_tools.py    # query_inventory, update_inventory_stock (rechazo explícito)
  tests/
    dev_idp.py             # Emisor OAuth de prueba local (RSA real, sin red) — nunca producción
    conftest.py
    test_auth_gate.py       # Middleware de MCP Auth en aislamiento (401/403 documentados)
    test_scopes.py
    test_incidents_tools.py
    test_inventory_tools.py
    test_server_integration.py  # Round-trip real: uvicorn + fastmcp.Client, JSON-RPC de verdad
  pyproject.toml / uv.lock / .venv / requirements.txt / .env.example / README.md

services/knowledge-api/     # el agente (ver Pasos/rag-knowledge-base-fase1.md) -- migrado a MCP
  agent_graph.py             # incidents_tool/inventory_tool ahora son nodos async; llaman a mcp_client.call_mcp_tool
  mcp_client.py               # cliente MCP del agente (langchain-mcp-adapters) -- NUEVO, reemplaza tools/ (eliminado)
  intent_extraction.py        # extract_incident_query/extract_inventory_query -- NUEVO, movidas de tools/*.py (eliminado)
  # eliminados: tools/incidents_tool.py, tools/inventory_tool.py, tools/backend_client.py

tests/pipelines/
  test_agent_graph.py        # actualizado: nodos/tests async, 2 evals de tool reescritos sin tools/ (eliminado)
  # eliminado: test_agent_tools.py (testeaba los módulos tools/*.py ya eliminados)
```

## Cómo correrlo

```bash
cd mcps/trackflow-mcp
uv sync
cp .env.example .env   # INCIDENTS_API_URL, INCIDENTS_API_TOKEN, MCPAUTH_ISSUER, ...
uv run python server.py
```

```bash
uv run pytest tests/     # 27 tests, sin red ni servicios corriendo
```

```bash
# Emisor OAuth de desarrollo (necesario para correr el servidor real o el
# agente contra él -- ver "Validación (MCP Playground)" más abajo)
cd mcps/trackflow-mcp
uv run python dev_idp_server.py   # sirve .well-known/* + POST /mint-token en :9999
```

## Checklist de la entrega — Servidor MCP

- [x] **MCP Server en Python bajo `mcps/`, con FastMCP**: `server.py`
  (`FastMCP(name="trackflow-mcp")`), 5 tools registradas con `@mcp.tool`.
- [x] **OAuth con MCP Auth (`mcpauth`), no la capa integrada de FastMCP**:
  `auth.py::build_mcp_auth_from_env()` arma un `MCPAuth` real (paquete
  `mcpauth` 0.1.1 de PyPI) descubriendo la metadata del `issuer` configurado
  vía su endpoint `.well-known/*` real (`fetch_server_config`). El
  middleware de bearer auth (`mcp_auth.bearer_auth_middleware("jwt", ...)`)
  se monta **solo** sobre el sub-app de FastMCP (`server.py::build_app()`),
  nunca se pasa `auth=` al constructor de `FastMCP` ni a `@mcp.tool` (los
  dos puntos donde viviría la capa de auth integrada que el checklist
  prohíbe).
- [x] **Tool obligatoria de tickets — crear, actualizar y consultar**:
  `tools/incidents_tools.py` — `query_incident` (`GET /api/incidents` /
  `GET /api/incidents/{id}`), `create_incident_ticket`
  (`POST /api/incidents`), `update_incident_status`
  (`PATCH /api/incidents/{id}/status`, **nunca** un PATCH genérico sobre el
  recurso completo — verificado en
  `test_update_incident_status_uses_the_lifecycle_endpoint_only`, que
  asserta el path exacto de la request capturada por
  `httpx.MockTransport`). Los mismos campos/enums que
  `services/incidents-api/models.py` (categorías, branches, orígenes,
  estados) están copiados como literales documentados en el schema de
  entrada de cada tool — no un string libre.
- [x] **Tool de solo consulta sobre inventario, con rechazo explícito de
  modificación**: `tools/inventory_tools.py::query_inventory` solo hace
  `GET /inventory/products` (nunca un verbo de escritura — verificado en
  `test_inventory_module_has_no_write_capability`, que lee el código fuente
  del módulo y falla si aparece `.post(`/`.put(`/`.patch(`/`.delete(`).
  Además de simplemente no registrar una tool de escritura, se expone
  **`update_inventory_stock_tool`** como tool real y descubierta por
  cualquier cliente MCP (aparece en `tools/list`, con su propósito
  documentado en la descripción) cuyo único comportamiento es devolver
  `{"ok": false, "error": "read_only_tool"}` — un rechazo explícito y
  descubrible, no la ausencia silenciosa de una capacidad (ver
  "Decisiones" para el porqué de esta interpretación del requisito).
- [x] **Cada tool documentada con nombre, descripción y schema de
  entrada/salida, descubrible sin contexto humano**: cada `@mcp.tool` trae
  un docstring que FastMCP usa como `description`, y los modelos Pydantic
  (`QueryIncidentInput`, `CreateIncidentTicketInput`, etc., todos con
  `ConfigDict(extra="forbid")`) generan el JSON Schema de entrada
  automáticamente — verificado listando las tools reales via
  `mcp.list_tools()` y, de punta a punta, via `fastmcp.Client.list_tools()`
  contra el servidor corriendo (`test_authenticated_client_with_scope_can_query_incident`).
- [x] **Los nombres de campo/IDs/valores de dominio coinciden con las APIs
  reales**: `VALID_INCIDENT_CATEGORIES`, `VALID_BRANCHES`,
  `VALID_INCIDENT_ORIGINS`, `VALID_INCIDENT_STATUSES` en
  `tools/incidents_tools.py` son una copia literal de los enums de
  `services/incidents-api/models.py` (leídos del archivo real antes de
  escribir la tool, no inventados).

## Checklist de la entrega — Autenticación y seguridad

- [x] **Ningún cliente sin access token válido puede listar ni invocar
  tools**: el middleware de `mcpauth` envuelve el sub-app de FastMCP
  completo (incluido `tools/list`, no solo `tools/call`) — verificado de
  punta a punta con `fastmcp.Client` real contra un servidor real corriendo
  (`test_unauthenticated_client_cannot_list_tools`: un cliente sin
  `Authorization` header no puede ni completar el handshake `initialize`).
- [x] **Principio de mínimo privilegio, con scopes**: 3 scopes
  (`incidents:read`, `incidents:write`, `inventory:read`) verificados por
  tool, no solo por el middleware global (ver "Decisiones" para el porqué:
  MCP Auth solo soporta un `required_scopes` por app, y las 5 tools
  comparten un único endpoint `/mcp`). `scopes.require_scope()` levanta
  `ScopeError` (código documentado `missing_required_scope`) si el
  `AuthInfo` verificado no trae el scope — probado en aislamiento
  (`tests/test_scopes.py`) y de punta a punta
  (`test_authenticated_client_without_required_scope_is_rejected_by_the_tool`:
  un token con `mcp:access` pero sin `incidents:write` sí completa el
  handshake, pero la tool misma lo rechaza).
- [x] **Códigos de error documentados para auth/autorización/validación, no
  un "error" genérico**:
  - Capa de transporte (`mcpauth`, antes de llegar a cualquier tool):
    `missing_auth_header`, `invalid_auth_header_format`,
    `missing_bearer_token`, `invalid_issuer`, `invalid_audience`,
    `invalid_token`, `missing_required_scopes` — códigos reales del
    paquete `mcpauth` (`mcpauth/exceptions.py::BearerAuthExceptionCode`,
    nunca reinventados), HTTP 401 salvo `missing_required_scopes` que es
    403 (verificado explícitamente,
    `test_request_missing_required_scope_gets_403_not_401`).
  - Capa de tool (scope específico faltante, ya con token válido):
    `missing_required_scope` (singular, distinto del código de `mcpauth`
    a propósito — ver docstring de `scopes.py`), propagado por FastMCP como
    `ToolError`.
  - Capa de negocio (falla del backend real): `timeout`, `not_found`,
    `unauthorized`, `connection_error:<detalle>`,
    `validation_error:<detalle>`, `invalid_transition:<detalle>`,
    `unexpected_status:<código>` — igual que en
    `services/knowledge-api/tools/*.py`, nunca un booleano `ok=False` sin
    explicación.
- [x] **Cada invocación de tool queda registrada (tool, cliente,
  resultado)**: `logging_middleware.py::ToolInvocationLoggingMiddleware`
  (hook `on_call_tool` de FastMCP, protocolo MCP en sí, no el transporte
  HTTP) — logea `tool=<nombre> client=<client_id o subject de AuthInfo>
  result=ok|error`. El `client_id` sale del `AuthInfo` ya verificado por
  `mcpauth`, nunca de un campo que la propia llamada a la tool pueda
  declarar.
- [x] **Protected Resource Metadata (RFC 9728) montada**: `mcpauth` 0.1.1 no
  la implementa (solo RFC 8414, `metadata_route()`) — se implementó a mano
  en `auth.py::protected_resource_metadata_route`
  (`/.well-known/oauth-protected-resource`), pública (sin auth), como
  `server.py::build_app()` la monta en el app raíz junto a la de RFC 8414.

## Checklist de la entrega — Validación (MCP Playground)

- [x] **Servidor real corriendo, con backend real detrás**: `services/incidents-api`
  levantado con Postgres real (contenedor Docker `postgres:16`, no un mock
  de SQLModel) + TinyDB local, un usuario creado, un ticket creado — ver
  "Cómo se verificó" para los comandos exactos. `mcps/trackflow-mcp`
  apuntado a ese backend real y al emisor OAuth de desarrollo
  (`dev_idp_server.py`, puerto 9999).
- [x] **Al menos un flujo completo por cada una de las 5 tools expuestas**:
  ejecutado con un cliente MCP real (`fastmcp.Client`) contra el servidor
  real — las 5 corridas y sus respuestas exactas están en "Cómo se
  verificó". Ninguna simulada.
- [x] **Comportamiento ante un intento de escritura sobre la tool de
  inventario, probado y documentado**: `update_inventory_stock_tool`
  invocada de verdad contra el servidor real → `{"ok": false, "error":
  "read_only_tool"}` — el mismo código documentado que garantiza
  `tests/test_inventory_tools.py`, ahora confirmado también en una corrida
  real, no solo en tests.
- [ ] **Probado en MCP Playground (mcpplaygroundonline.com) vía URL pública
  de Codespaces**: el servidor quedó corriendo y verificado end-to-end con
  un cliente MCP real (ítems anteriores) — el paso de exponer el puerto
  como público (`gh codespace ports visibility 8010:public`) requiere una
  acción que un guardrail de seguridad de este entorno bloquea para mí
  (crear un túnel de ingreso externo), así que ese último paso manual
  (marcar el puerto público + pegar la URL/token en el sitio) quedó para el
  desarrollador — ver "Pendiente" para las instrucciones exactas y cómo
  generar el token.

## Checklist de la entrega — Migración del agente

- [x] **El agente conectado al MCP Server via `langchain-mcp-adapters`**:
  `services/knowledge-api/mcp_client.py::call_mcp_tool()` — usa
  `MultiServerMCPClient` (transporte `streamable_http`) real, no un cliente
  HTTP a mano. Reemplaza el nodo que llamaba directo a
  `services/incidents-api` (`tools/incidents_tool.py::query_incidents`,
  ahora eliminado).
- [x] **Implementación anterior eliminada, no solo deprecada**:
  `services/knowledge-api/tools/` (los tres archivos: `incidents_tool.py`,
  `inventory_tool.py`, `backend_client.py`) y
  `tests/pipelines/test_agent_tools.py` (testeaba esos módulos) se
  borraron del repo — el agente tiene un único camino posible hacia el
  Incidents Manager. `agent_graph.py` ya no importa nada de HTTP directo
  hacia `incidents-api`.
- [x] **El enrutamiento existente (RAG vs. tools) sigue funcionando
  igual**: `classify_intent`, `_route_after_classify`,
  `_route_after_incidents_tool`, `_route_after_inventory_tool`, el camino
  `"both"` — **ninguno se tocó**. Lo único que cambió es qué hay *dentro*
  de los nodos `incidents_tool`/`inventory_tool` (antes: HTTP directo;
  ahora: `await call_mcp_tool(...)`) — mismo contrato de salida
  (`{"ok", "incidents"|"products", "error"}`) así que
  `_tool_result_to_context_chunks()` tampoco se tocó. Confirmado con los 10
  tests de `test_agent_graph.py` (mismos 10 escenarios que antes de migrar,
  todos en verde) más una corrida real end-to-end contra el MCP Server real
  (ver "Cómo se verificó").

## Cómo se verificó

No hay un proveedor OAuth 2.1 / OIDC real configurado en este repo (ni
credenciales de Auth0/Logto/Keycloak/Okta). Antes de escribir una sola
línea de `auth.py` o `server.py`, leí el código fuente real de los dos
paquetes que iba a usar (`mcpauth` 0.1.1 y `fastmcp-slim` 4.0.10,
descargados con `pip download --no-deps` e inspeccionados directamente,
nunca asumidos por nombre) para no adivinar una API que no existe:

1. **`mcpauth` real**: `MCPAuth.__init__`, `.bearer_auth_middleware()`,
   `.metadata_route()`, `.auth_info`, `mcpauth.utils.create_verify_jwt`
   (acepta una `PyJWK` en memoria, no solo una URL de JWKS — la pieza clave
   para poder testear sin red), y los códigos de excepción reales
   (`mcpauth/exceptions.py`) en vez de inventar nombres de error
   "razonables".
2. **`fastmcp-slim` real**: `FastMCP.http_app(middleware=[...])` acepta
   middleware ASGI de Starlette (no el `Middleware` interno de FastMCP, que
   es para otra cosa), `fastmcp.server.middleware.Middleware` con el hook
   `on_call_tool` para trazabilidad, y que el parámetro `auth=` del
   constructor de `FastMCP`/`@mcp.tool` es exactamente la capa integrada
   que el checklist pide evitar — confirmado leyendo `server.py` del
   paquete antes de decidir no usarlo.
3. **Emisor de prueba real, no una función que "finge" verificar un
   JWT**: `tests/dev_idp.py` genera un par de claves RSA (`cryptography`) y
   firma JWTs RS256 reales (`PyJWT`) — los tests corren la misma
   verificación de firma que correría contra un proveedor real
   (`mcpauth.utils.create_verify_jwt` con la `PyJWK` pública del emisor de
   prueba), documentado explícitamente como stand-in de desarrollo/test,
   nunca usable en producción (`auth.py`, sección "Producción vs.
   desarrollo/tests").
4. **Bug real encontrado y corregido — validación de metadata OAuth**: el
   primer intento de `MCPAuth(server=...)` con una `AuthorizationServerMetadata`
   mínima (issuer/authorization_endpoint/token_endpoint/jwks_uri/
   response_types_supported) falló con
   `MCPAuthAuthServerException: The server configuration does not match the
   MCP specification` — `mcpauth` exige soporte de PKCE (RFC 7636)
   declarado (`code_challenge_methods_supported` debe incluir `"S256"`) para
   considerar válida la metadata. Encontrado corriendo
   `tests/test_auth_gate.py` por primera vez, no adivinado de antemano —
   corregido agregando `code_challenge_methods_supported=["S256"]` en
   `auth.py::build_auth_server_config`.
5. **Bug real encontrado y corregido — extracción del resultado de
   `fastmcp.Client`**: `result.data` de un `CallToolResult` para una tool
   que devuelve un modelo Pydantic no es un `dict` sino un objeto `Root`
   generado dinámicamente (`fastmcp.utilities.json_schema_type.Root`), no
   subscriptable — encontrado corriendo
   `test_authenticated_client_with_scope_can_query_incident` por primera
   vez (`TypeError: 'Root' object is not subscriptable`). Corregido usando
   `result.structured_content` (el `dict` plano), confirmado inspeccionando
   ambos atributos con un script exploratorio antes de decidir cuál usar.
6. **Bug real encontrado y corregido — falso positivo en el test de "sin
   capacidad de escritura"**: `test_inventory_module_has_no_write_capability`
   fallaba porque el propio docstring del módulo *mencionaba* `.post(` /
   `.put(` / `.patch(` / `.delete(` como texto explicativo — el test
   detectaba su propia documentación, no código real. Corregido
   reformulando el docstring para no citar los verbos literalmente.
7. **Round-trip end-to-end real, no solo unitario**:
   `tests/test_server_integration.py` levanta `server.build_app()` completo
   (Starlette + FastMCP + `mcpauth`) en un thread de `uvicorn` real sobre un
   socket real de `127.0.0.1` (puerto 0, resuelto dinámicamente), y lo
   consulta con `fastmcp.Client` (el cliente MCP real) — `initialize`,
   `tools/list`, `tools/call`, streamable-HTTP real, sin dobles en el
   protocolo ni en el transporte. Solo las llamadas salientes hacia
   `services/incidents-api` se interceptan (`httpx.MockTransport` via
   monkeypatch de `httpx.Client`, mismo patrón que el resto del repo) para
   no depender de un servicio corriendo. 4 escenarios, los 4 en verde: sin
   token (bloqueado), con token y scope correcto (tool ejecuta y responde),
   con token pero sin el scope de la tool (rechazado por la tool, código
   documentado), e intento de escritura de inventario (rechazado
   explícitamente).
8. **27 tests en total, los 27 en verde** (`uv run pytest tests/` desde
   `mcps/trackflow-mcp/`): 5 de auth gate en aislamiento, 4 de
   `scopes.py`, 8 de `incidents_tools.py`, 6 de `inventory_tools.py`, 4 de
   integración end-to-end.
9. **Bug real encontrado y corregido — `auth.py` nunca cargaba `.env`**: al
   levantar `server.py` por primera vez contra un `.env` real (no inyectado
   por tests), falló con
   `RuntimeError: MCPAUTH_ISSUER no esta configurado` a pesar de que
   `MCPAUTH_ISSUER` sí estaba en `.env`. Causa: `auth.py` lee
   `os.environ.get("MCPAUTH_ISSUER", ...)` a nivel de módulo, pero solo
   `backend_client.py` llamaba `load_dotenv()` — y `server.py` importa
   `auth` **antes** que `tools/*` (que es lo que arrastra
   `backend_client.py`), así que `.env` todavía no se había cargado cuando
   `auth.py` leía la variable. No lo cubría ningún test porque los tests
   inyectan `MCPAuth` directamente (`test_mcp_auth` fixture), sin pasar por
   `build_mcp_auth_from_env()`. Corregido agregando `load_dotenv()` al
   propio `auth.py`.
10. **Backend real levantado para la validación, no solo `httpx.MockTransport`**:
    para probar las 5 tools con datos genuinos (no simulados, checklist
    ⚠️ IMPORTANTE) se levantó `services/incidents-api` con un Postgres real
    (`docker run postgres:16`, tablas creadas por
    `SQLModel.metadata.create_all()` en el startup real del servicio) +
    Redis real + TinyDB local, se creó un usuario
    (`POST /users`, `POST /auth/login`) y un ticket
    (`POST /api/incidents`) reales. El inventario se auto-sembró al primer
    `GET /inventory/products` (`seed_inventory_if_empty`, ya existente en
    `routers/inventory.py`).
11. **`dev_idp_server.py` — promovido de `tests/dev_idp.py` a un proceso
    real**: un test genera su propia clave RSA y listo, pero validar
    manualmente (Playground) y correr el agente real necesitan un emisor
    que siga vivo entre llamadas y sirva `.well-known/*` por HTTP de
    verdad — `dev_idp_server.py` (`uv run python dev_idp_server.py`, puerto
    9999) hace exactamente eso, con un endpoint extra `POST /mint-token`
    (atajo de desarrollo documentado, no parte de OAuth) para emitir tokens
    bajo demanda.
12. **Las 5 tools ejecutadas de verdad contra el servidor real + el backend
    real** (checklist "Validación", "al menos un flujo completo por cada
    tool"), con `fastmcp.Client` apuntando a `http://localhost:8010/mcp` y
    un token minteado con los 4 scopes:
    - `query_incident_tool({"incident_id": 1})` → `ok: true`, trae el
      ticket real recién creado.
    - `create_incident_ticket_tool(...)` → `ok: true`, crea un ticket
      nuevo real (`id: 2`) en el backend real.
    - `update_incident_status_tool({"incident_id": 2, "status":
      "in_progress"})` → `ok: true`, el `status` cambia de verdad en la
      base (vía el endpoint de ciclo de vida real).
    - `query_inventory_tool({"sku": "TEC-EAR-001"})` → `ok: true`, trae el
      producto real sembrado.
    - `update_inventory_stock_tool(...)` → `ok: false, error:
      "read_only_tool"` — el rechazo explícito, confirmado en una corrida
      real (no solo en el test).
13. **Migración del agente verificada con una corrida real de `run_agent()`
    contra el MCP Server real** (no solo con fakes): con
    `MCP_SERVER_URL`/`MCP_SERVER_TOKEN` apuntando al servidor real,
    `await agent_graph.run_agent("¿cuál es el estado del ticket 1?", ...)`
    produjo `node_order = ["receive_question", "classify_intent",
    "incidents_tool", "generate"]` y una respuesta con los datos reales del
    ticket; la pregunta de inventario produjo el mismo patrón con
    `inventory_tool`. `retrieve_fn` se inyectó como una función que lanza
    `AssertionError` si se llega a llamar — nunca se llamó, confirmando que
    el enrutamiento eligió la tool y no el RAG, igual que antes de migrar.
    También se probó `POST /agent/query` de punta a punta con
    `TestClient` (mismo patrón que toda la sesión) contra el servidor MCP
    real → `200` con la respuesta correcta.
14. **Bug de LangGraph verificado antes de asumirlo, no después**: antes de
    convertir los nodos de tool a `async def`, se armó un grafo mínimo de
    prueba (dos nodos, uno sync y uno async) y se confirmó con
    `.ainvoke()`/`.astream()` que LangGraph efectivamente soporta nodos
    sync y async mezclados en el mismo grafo — evitando migrar
    innecesariamente los nodos `retrieve`/`generate`/`classify_intent`
    (que no lo necesitan) solo por precaución.
15. **Fragilidad preexistente encontrada al correr toda la suite junta**:
    `pytest test_rag.py test_agent_graph.py` en una invocación falla en la
    importación de `agent_graph.py` por una colisión de `sys.modules['rag']`
    entre los dos `rag.py` del repo (`data/process/` vs. `data/pipelines/`)
    -- preexistente, no introducida por esta migración (no se tocó
    `pipeline_path.py` ni el import de `rag` en `agent_graph.py`). Cada
    archivo, corrido en su propia invocación de `pytest` (el patrón que ya
    usaba todo este repo), sigue en verde -- documentado en
    `Pasos/rag-knowledge-base-fase1.md`, "Pendiente" #10.

## Decisiones de implementación no cubiertas por la guía genérica

- **HTTP, no en-proceso, hacia `services/incidents-api`**: mismo
  razonamiento que `services/knowledge-api/tools/*.py` — son
  procesos/paquetes separados en este monorepo (cada uno con su propio
  `pyproject.toml`/`.venv`/deploy), así que "en-proceso" no aplica.
- **Scopes verificados a mano por-tool, no solo via `required_scopes` del
  middleware**: `mcpauth.bearer_auth_middleware(required_scopes=[...])`
  acepta una sola lista para todo el ASGI app que protege, pero las 5 tools
  de este servidor viven bajo un único endpoint MCP (`/mcp`, todas las
  invocaciones son `POST /mcp` con `method: "tools/call"` y el nombre de la
  tool en el *body* JSON-RPC, no en la URL) — no hay forma de aplicar un
  `required_scopes` distinto por tool a nivel de ruta HTTP. Por eso el
  middleware exige solo el scope base `mcp:access` (permite descubrir qué
  tools existen), y cada tool verifica su scope específico con
  `scopes.require_scope()` al entrar, documentado en detalle en
  `scopes.py`.
- **RFC 9728 (Protected Resource Metadata) escrito a mano**: `mcpauth`
  0.1.1 (la versión más reciente en PyPI al momento de esta entrega) solo
  implementa RFC 8414 (Authorization Server Metadata). Como RFC 9728 define
  un documento de descubrimiento público y estático (identificador del
  recurso + lista de authorization servers), implementarlo a mano no es
  simular un dato de negocio — es completar un endpoint de protocolo que la
  librería todavía no trae.
- **Endpoints de metadata públicos, fuera del middleware de auth**:
  `server.py::build_app()` monta el middleware de `mcpauth` **solo** sobre
  el sub-app de FastMCP (`Mount("/", app=mcp_app)`), nunca sobre el app
  Starlette raíz completo — un cliente necesita leer la metadata *antes* de
  tener un token (problema del huevo y la gallina si las rutas
  `.well-known/*` también exigieran auth).
- **Quinta tool (`update_inventory_stock_tool`) que siempre rechaza**:
  el checklist dice "cualquier intento de modificación debe ser rechazado
  explícitamente por el servidor, no simplemente omitido" — interpretado
  literalmente como que la ausencia de una tool de escritura no basta por
  sí sola (un cliente que la busque y no la encuentre recibe un error de
  protocolo genérico de "tool no existe", no un rechazo de negocio
  explicado). Se expone una tool real, descubierta en `tools/list`, cuyo
  contrato de entrada es honesto (`sku`, `quantity_delta`) pero cuyo cuerpo
  nunca llama al backend y siempre devuelve `read_only_tool`.
- **Emisor OAuth de prueba en vez de mockear la verificación de firma**:
  se podría haber probado el middleware con una función `verify_fn` falsa
  que simplemente devuelve un `AuthInfo` fijo sin verificar nada — se
  descartó esa opción porque no probaría que la lógica de seguridad real
  (firma RS256, coincidencia de issuer, audiencia, scopes) funciona; el
  emisor de prueba con claves RSA reales sí lo hace, sin depender de un
  proveedor externo ni de red.
- **`mcp_client.py::call_mcp_tool` arma un `ToolCall` (`{"name", "args",
  "id", "type": "tool_call"}`), no pasa los argumentos planos a
  `tool.ainvoke()`**: confirmado empíricamente (no asumido) que
  `tool.ainvoke(args_planos)` devuelve solo el `content` (el JSON
  serializado como *texto*), mientras que `tool.ainvoke(tool_call)`
  devuelve un `ToolMessage` cuyo `.artifact["structured_content"]` ya es
  el dict real -- evita tener que parsear JSON a mano y es exactamente el
  mismo dict que devolvía la tool HTTP directa que se reemplazó.
- **`call_mcp_tool` reconstruye el cliente MCP y vuelve a listar las tools
  en cada llamada, sin cachear una sesión persistente**: mismo trade-off
  que `httpx.Client()` fresco en cada llamada de la implementación HTTP
  directa que reemplaza -- listar 5 tools es una llamada MCP liviana
  (`tools/list`), y mantener una sesión MCP persistente viva a través de
  llamadas HTTP individuales del agente introduciría gestión de ciclo de
  vida (cuándo reconectar, cuándo expira el token) que esta entrega no
  necesita todavía.
- **`MCP_TIMEOUT_SECONDS` por defecto en 8s, no los 4s que tenía
  `INCIDENTS_API_TIMEOUT_SECONDS`**: una llamada MCP implica un handshake
  de protocolo (`tools/list` + `tools/call`, cada uno un JSON-RPC sobre
  streamable-HTTP) encima del tiempo del backend real -- se mantiene el
  mismo espíritu (valor concreto y corto, no "razonable") pero ajustado al
  overhead real del transporte nuevo.
- **`dev_idp_server.py` vive en `mcps/trackflow-mcp/` (no en
  `services/knowledge-api/`)**: es el emisor que protege al MCP Server, no
  una pieza del agente -- el agente solo lo consume indirectamente (el
  token que usa para llamar al MCP Server debe venir de ese mismo emisor).
  Vive junto a `auth.py`, que es quien lo consumiría en un chequeo real.

## Pendiente / siguientes pasos

- **No probado contra un proveedor OIDC real** (Auth0/Logto/Keycloak/Okta):
  `auth.py::build_mcp_auth_from_env()` usa `fetch_server_config()` (HTTP
  real a `.well-known/openid-configuration`), pero no hay credenciales de
  ningún proveedor en este repo para un test de humo contra uno real. El
  camino de producción está escrito y documentado, no ejecutado
  end-to-end.
- **Sin Dockerfile/entrada en `docker-compose.yml`**: el checklist de esta
  entrega no lo pide explícitamente (a diferencia de milestones previos);
  se agregó `requirements.txt` por consistencia con el resto del repo, pero
  no se dockerizó — si se necesita, seguiría el patrón de
  `services/knowledge-api/Dockerfile`.
- **Rate limiting / protección contra abuso no implementada**: fuera del
  alcance de este checklist (autenticación/autorización sí, throttling no).
- **Logging solo a stdout** (`logging.getLogger("trackflow_mcp.tool_invocations")`):
  cumple "registrar en logs", pero no hay un backend de logs centralizado
  configurado en este repo (no hay convención previa de logging estructurado
  a un colector en el resto del monorepo tampoco).
- **Falta el último paso manual de "Validación": probar en MCP Playground
  de verdad**. El servidor real (`mcps/trackflow-mcp`, puerto 8010) y su
  emisor OAuth de desarrollo (`dev_idp_server.py`, puerto 9999) están
  **corriendo ahora mismo** en este Codespace, contra un `incidents-api`
  real (Postgres + TinyDB reales, con un ticket real ya creado) -- dejados
  así a propósito para este paso. Falta:
  1. Exponer el puerto 8010 como público. Yo no puedo ejecutar este paso
     (`gh codespace ports visibility 8010:public`) -- un guardrail de este
     entorno lo bloquea por tratarse de crear un túnel de ingreso externo,
     y me pidió dejarlo para que decida el desarrollador. Alternativa sin
     `gh`: en el panel "Ports" de VS Code, click derecho sobre el puerto
     8010 → "Port Visibility" → "Public".
  2. La URL pública queda con el patrón
     `https://$CODESPACE_NAME-8010.app.github.dev/mcp` (en este Codespace:
     `https://solid-happiness-gx6r7rpv454cp455-8010.app.github.dev/mcp`).
  3. Generar un token de prueba (el emisor de desarrollo sigue corriendo en
     `localhost:9999`):
     ```bash
     curl -s -X POST http://localhost:9999/mint-token \
       -H "Content-Type: application/json" \
       -d '{"scopes": ["mcp:access", "incidents:read", "incidents:write", "inventory:read"], "audience": "trackflow-mcp"}'
     ```
     (el campo `access_token` de la respuesta es el Bearer token a pegar).
  4. En mcpplaygroundonline.com: pegar la URL del paso 2, expandir la
     sección de auth y pegar el token del paso 3, conectar, y correr
     `tools/list` + al menos una llamada por tool (ya ejecutadas por mí vía
     `fastmcp.Client` con resultados reales documentados en "Cómo se
     verificó" #12 -- este paso es para confirmarlo también desde
     Playground, como pide el checklist literalmente).
  5. Limpieza posterior: los contenedores `trackflow-pg-mcp`/
     `trackflow-redis-mcp` y los procesos `dev_idp_server.py`/`server.py`/
     `uvicorn main:app` (incidents-api) quedaron corriendo para este paso --
     una vez validado, `docker rm -f trackflow-pg-mcp trackflow-redis-mcp`
     y matar esos procesos (no se automatizó el apagado para no cortar la
     validación a mitad de camino).
- **El token del agente hacia el MCP Server (`MCP_SERVER_TOKEN`) se generó
  a mano con el emisor de desarrollo, no vía un flujo OAuth
  client-credentials real**: documentado como límite explícito en
  `mcp_client.py` -- en producción, ese token saldría de un flujo
  client-credentials real contra `MCPAUTH_ISSUER`, renovado
  periódicamente; no implementado por no haber un proveedor real
  configurado (mismo límite que el resto del proyecto).
