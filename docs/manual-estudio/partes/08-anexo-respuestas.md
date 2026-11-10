
---

<a id="anexo-a"></a>
## Anexo A — Respuestas de autoevaluación

### Sección 1 — Visión general

- **P1.1** La última etapa de un envío: del almacén o centro de distribución hasta la puerta del cliente final.
- **P1.2** Cualquiera de estos: almacenes sin visibilidad de stock compartida; seguimiento manual en los portales de 8 transportistas; devoluciones revisadas una a una (18-25 %); 80 % de consultas atendidas por una persona; sin CRM; informe semanal montado a mano los domingos.
- **P1.3** Backoffice: operarios de almacén, coordinadores, equipo comercial y técnico (personal interno). Agente CX: clientes B2B (marcas) y B2C (destinatarios). ⚠️ Hoy, en la práctica, solo pueden usarlo usuarios con cuenta del backoffice (no hay cuentas de clientes).
- **P1.4** Porque es un solo repositorio con muchos proyectos dentro: 2 frontends, 4 servicios backend, un servidor MCP, pipelines de datos e IA, scripts e infraestructura.

### Sección 2 — Arquitectura

- **P2.1** El agente CX está en `services/knowledge-api` (`agent_graph.py`). El flujo de RFP vive en `data/pipelines/rfp_intake/` y se dispara desde `services/incidents-api/routers/rfp.py` mediante Celery.
- **P2.2** PostgreSQL: datos de negocio y analítica (inventario, telemetría, RFP, KPIs, jobs). TinyDB: usuarios, perfiles, incidencias, proveedores y DLQ (herencia de hitos antiguos). Redis: cola de Celery y memoria del agente. Qdrant: vectores de la base de conocimiento para el RAG.
- **P2.3** SSE solo va del servidor al navegador; WebSocket va en los dos sentidos. SSE: avisos de RFP nuevas (`GET /rfp/events`). WebSocket: chat con el agente (`/chat/ws`), porque el usuario necesita interrumpir.
- **P2.4** Para tener un único camino controlado, con autenticación propia (OAuth 2.1), permisos por herramienta (scopes), registro de cada invocación y la posibilidad de que cualquier agente compatible use las mismas tools.

### Sección 3 — Stack

- **P3.1** Valida que los datos tienen la forma y los tipos esperados. `extra="forbid"` rechaza cualquier campo que no esté declarado (por ejemplo, el antiguo `authorized_order_ids` ahora da 422).
- **P3.2** Para responder enseguida (202) y hacer el trabajo pesado en otro proceso, con reintentos, una cola que sobrevive a reinicios y una DLQ para los fallos.
- **P3.3** Permite modelar el agente como un grafo con estado: ramas condicionales, pasos en paralelo, checkpoints (guardar y retomar), *streaming* de tokens y pausas para aprobación humana con `interrupt()`.
- **P3.4** Con solo 120 meses de datos, XGBoost (boosting secuencial) aporta poco y sobreajusta con más facilidad. Random Forest funciona bien con valores por defecto y da `feature_importances_` directamente.
- **P3.5** uv es un gestor de dependencias Python muy rápido. `uv.lock` fija las versiones exactas de todas las librerías, así cualquiera instala exactamente lo mismo.

### Sección 4 — Carpetas

- **P4.1** Lógica: `data/pipelines/rfp_intake/`. Endpoints HTTP: `services/incidents-api/routers/rfp.py` (y `rfp_events.py` para el SSE).
- **P4.2** `projectbrief.md` (negocio), `techContext.md` (stack y decisiones) y `progress.md` (hitos). Lo lee el **asistente de IA que programa**, al empezar cada sesión, por obligación de `AGENTS.md`.
- **P4.3** `agents/_template/agent.py` (vacío), `skills/_template/SKILL.md` (vacío), `skills/code-review`, `skills/research`, `workflows/`, `internal/`, `shared/`, `audit/before` y `audit/after`. Es importante para no afirmar en la defensa que existen agentes, skills o workflows "propios" en esas carpetas.
- **P4.4** Guarda la evidencia antes/después de la auditoría OWASP (paso 34): salidas de `pip-audit` y `npm audit`, puertos de Docker, verificación del endurecimiento y resultados de los tests de seguridad.

### Sección 5 — Pasos

- **P5.1** Para tener una sola fuente de verdad: el stock siempre es entradas − salidas, así que no puede descuadrarse un contador. Coste: cada consulta hace dos agregaciones.
- **P5.2** Paso 2 (solo 3 de 9 categorías; validación no extraída a `packages/shared`); paso 18 (sin medición Lighthouse, hook en 2 de 4 formularios, sin `<FormField>`); y piezas pendientes en otros: el cron sin instalar (21), la corrección del sobreajuste (24), la prueba en MCP Playground (26). Causas: falta de documentos, de navegador o de servidor en el entorno.
- **P5.3** En el paso 25 el agente llamaba a `incidents-api` por HTTP directo (`tools/*.py`). En el 26 esas tools se eliminaron y el agente pasa por el servidor MCP (`mcp_client.py` + `langchain-mcp-adapters`), con OAuth y scopes. El enrutamiento no cambió.
- **P5.4** *Dead Letter Queue*: el lugar donde se guardan las tareas que fallaron definitivamente para revisarlas. Aparece en el paso 22 (`task_dlq` en TinyDB).
- **P5.5** El error en validación (46.598 €) es 2,07 veces el de entrenamiento (22.517 €): el modelo memoriza. Lo corregiría simplificando los árboles (subir `min_samples_leaf`, bajar `max_depth`) y volviendo a evaluar con `TimeSeriesSplit`.

### Sección 6 — Flujos

- **P6.1** Nada grave: el servidor recalcula el stock y responde 400 si no hay suficiente. La validación del navegador es solo comodidad.
- **P6.2** Límite de longitud, rate limit por usuario, normalización Unicode, `input_guard` (incluido el ACL de pedidos), validación de argumentos de la tool, autenticación y scope en el MCP, saneamiento del contenido externo y `output_guard`.
- **P6.3** Porque la petición se **acepta**, pero el trabajo aún no está hecho: se procesa después en Celery. 202 significa "aceptado, en proceso".
- **P6.4** Cuando el nodo `classify` declara la RFP como válida, antes de que terminen los workers. El evento se escribe en el outbox en la misma transacción que los metadatos.

### Sección 7 — IA

- **P7.1** Llamar: usar un modelo ya entrenado a través de su API (el LLM de generación, el de embeddings). Entrenar: ajustar un modelo con tus datos (el Random Forest de ventas, con 2016-2023).
- **P7.2** El LLM no se sabe de memoria las políticas de TrackFlow. Antes de responder, el sistema busca en la base de conocimiento los fragmentos más parecidos a la pregunta y se los da como "libro abierto"; el LLM responde apoyándose en ellos.
- **P7.3** Porque se midió con un embedding léxico de sustitución, no con el modelo real; solo son 10 preguntas; y de los 8 aciertos solo 3 superan el umbral `min_score` que usa el sistema.
- **P7.4** `classify_intent`, la propuesta y la decisión de memoria, el clasificador de RFP, los workers, los generadores, los evaluadores y el árbitro. Todos son reglas y plantillas.

### Sección 8 — Agentes

- **P8.1** Una tool es una función concreta (consultar una incidencia). El servidor MCP es el "enchufe" que expone varias tools de forma estándar, con descubrimiento y autenticación.
- **P8.2** Porque el cliente MCP del agente solo permite `query_incident_tool` y `query_inventory_tool` (`AGENT_ALLOWED_MCP_TOOLS`), sean cuales sean los permisos de su token (paso 34).
- **P8.3** El asistente de IA que programa. Le da contexto de negocio, stack y estado al empezar cada sesión, para no perder información ni duplicar trabajo.
- **P8.4** Detecta si cambiaron los tipos compartidos de `packages/shared/types/**`, clasifica los cambios como `compatible`, `breaking` o `unknown` y devuelve `PASS`, `FAIL` o `NO_CONTRACT_CHANGES`. Se ejecutaría antes de un commit o un PR.

### Sección 9 — Decisiones

- **P9.1** Porque `EventSource` no permite enviar la cabecera `Authorization` con el JWT, y el stream debe estar protegido.
- **P9.2** No tiene transacciones ni control de concurrencia, y el archivo `suppliers.json` (con usuarios y hashes de contraseña, incluido un admin) está versionado en git.
- **P9.3** Los hechos se buscan por clave exacta (`carrier:país`), no por parecido. Redis es lo adecuado (rápido, con caducidad) y, además, separa la memoria de la base de conocimiento.
- **P9.4** La propuesta era un monolito modular (`backend/app/domains/...`). Se construyeron varios servicios separados (incidents-api, knowledge-api, reporting, job_runner) más `data/pipelines`, que comparten base de datos y secreto JWT.

### Sección 10 — Código

- **P10.1** Devuelve 0. `coalesce(SUM(...), 0)` convierte el `NULL` de "no hay filas" en 0, y `int(... or 0)` es una segunda protección.
- **P10.2** Porque un CSV mal formado fallaría exactamente igual en cada intento: reintentar solo gasta tiempo del worker.
- **P10.3** El grafo queda detenido y su estado completo se guarda en Postgres (`PostgresSaver`). No consume recursos. Cuando alguien aprueba, `Command(resume=...)` lo retoma justo en ese punto.
- **P10.4** Un 429 (o un evento `error` en el chat) con `Retry-After` de unos 10 s: cuando la llamada más antigua de la ventana cumpla 60 s, se libera un cupo.

### Sección 11 — Ejecución

- **P11.1** `SUPABASE_DATABASE_URL` (o `DATABASE_URL`).
- **P11.2** Porque `incidents-api` firma los tokens con ese secreto y los demás servicios los verifican con el mismo. Si es distinto, rechazan el token (401).
- **P11.3** Porque cada servicio tiene sus propias dependencias y su propio `.venv` (por ejemplo, Celery solo en incidents-api y Qdrant solo en knowledge-api).

### Sección 12 — Limitaciones

- **P12.1** Respuesta abierta. Buenas candidatas: sin LLM real verificado (calidad desconocida), sin segmentación B2B (fuga entre marcas), usuarios en TinyDB versionado en git, telemetría sin allowlist y sin login (datos falsos en los KPIs).
- **P12.2** Se pierde al reiniciar el servicio y no se comparte entre varios workers: un usuario conectado al worker A no recibiría los tokens generados en el worker B.
- **P12.3** Porque el compose define `NEXT_PUBLIC_API_URL` pero el backoffice lee `NEXT_PUBLIC_INCIDENTS_API_URL` (por defecto `localhost:8001`), y además `backend:8000` es un nombre interno de Docker que el navegador no resuelve.

### Sección 13 — Errores

- **P13.1** 401: no se sabe quién eres (sin token o con un token inválido), por ejemplo `GET /inventory/orders` sin login. 403: se sabe quién eres, pero no tienes permiso, por ejemplo un usuario normal que intenta crear un `manager`.
- **P13.2** 429 *Too Many Requests*, con la cabecera `Retry-After` (segundos que hay que esperar).
- **P13.3** El servidor cerró el WebSocket porque el token falta, es inválido o ha caducado. El cliente no reintenta porque reintentar con el mismo token fallaría siempre: hay que volver a iniciar sesión.
