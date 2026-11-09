
---

<a id="s5"></a>
## 5. Los pasos del proyecto

La carpeta `Pasos/` no tiene números en los nombres. Aquí se numeran por **orden cronológico real**: la fecha en que cada archivo entró por primera vez en git (`git log --diff-filter=A`). Así la numeración refleja cómo creció el proyecto de verdad.

**Estados posibles**

- ✅ **Implementado**: lo descrito existe en el código actual.
- 🔄 **Modificado después**: se implementó, pero un paso posterior lo cambió (el código actual es distinto de lo que dice el paso).
- 🟡 **A medias**: parte se hizo y parte no.
- ❌ **Descartado**: se hizo y luego se eliminó (solo afecta a piezas sueltas dentro de algunos pasos; ningún paso entero está descartado).

### 5a. Versión esquemática

| # | Archivo | Resumen en una línea | Estado actual |
| --- | --- | --- | --- |
| 1 | `recuperacion-contrasena.md` | Olvidé mi contraseña, restablecer y cambiar contraseña (API + pantallas) | 🔄 Implementado; el hash de contraseñas cambió a scrypt (paso 34) |
| 2 | `gestion-incidencias.md` | Gestor de incidencias: modelo, seed desde CSV, API y paneles | 🟡 Solo 3 de las 9 categorías existen; validación no extraída a `packages/shared` |
| 3 | `gestion-errores.md` | Manejo de errores en frontend, backend y scripts | ✅ |
| 4 | `integracion-api-inventario.md` | Módulo `inventory.ts` que centraliza las llamadas a `/inventory` | ✅ |
| 5 | `inventario-productos-ordenes.md` | Página de productos y formulario de orden de entrada | ✅ |
| 6 | `inventario-salida-historial.md` | Orden de salida con aviso de stock e historial de movimientos | ✅ |
| 7 | `proteccion-rutas-inventario.md` | Las 4 páginas de inventario exigen login | ✅ (la protección real del servidor llegó en el paso 34) |
| 8 | `docker-compose-fullstack.md` | Contenedores para frontends y backend con recarga en caliente | 🔄 Hoy hay 8 servicios; puertos internos a 127.0.0.1 (paso 34) |
| 9 | `usememo-oportunidad-incidents-panel.md` | Optimización `useMemo` en la tabla de incidencias | ✅ |
| 10 | `registro-ordenes.md` | Registro de las 9 órdenes de la sesión de optimización | ✅ (documento índice) |
| 11 | `lazy-loading-candidatos-nextjs.md` | Carga diferida de `LandingInteractions` y `QuoteForm` | ✅ |
| 12 | `analisis-endpoints-fastapi-coste-frecuencia.md` | Inventario de endpoints con coste y frecuencia | ✅ (análisis; varios endpoints cambiaron después) |
| 13 | `implementacion-caching-endpoints.md` | Caché en memoria con TTL para `/suppliers` y `/auth/me` | ✅ |
| 14 | `candidatos-caching-endpoints.md` | Por qué esos dos endpoints y no otros | ✅ |
| 15 | `telemetria-trackflow-resumen.md` | Captura de 13 de 15 eventos en el backoffice | ✅ (2 eventos sin cablear) |
| 16 | `telemetria-almacenamiento-supabase.md` | Tabla `telemetry_events` y carga por lotes con rechazo parcial | ✅ |
| 17 | `telemetria-pipeline-analisis-reporte.md` | Análisis con pandas y `GET /telemetry/report` | 🔄 El informe exige JWT desde el paso 34; la caché prevista nunca se hizo |
| 18 | `auditoria-web-performance.md` | Auditoría Lighthouse y refactor de formularios | 🟡 Sin medición Lighthouse; hook en 2 de 4 formularios; `<FormField>` no existe |
| 19 | `telemetria-diseno-pipeline-reporting-ejecutivo.md` | Diseño (sin código) del pipeline de KPIs semanales | ✅ Implementado en el paso 20, con desviaciones |
| 20 | `telemetria-pipeline-implementacion.md` | Pipeline Prefect + servicio `reporting` | ✅ (sin deployment de Prefect; nunca probado con Supabase real) |
| 21 | `telemetria-nightly-export-job-runner.md` | Exportación nocturna, tabla `ops.job_runs`, bloqueo e idempotencia | ✅ (el cron no está instalado en ningún servidor) |
| 22 | `incidents-analyze-celery-redis.md` | Análisis de CSV en segundo plano con Celery, reintentos y DLQ | 🔄 Redis y Flower pasaron a 127.0.0.1 (paso 34) |
| 23 | `sales-forecast-model.md` | Modelo de predicción de ingresos (Random Forest) | 🔄 El dataset sintético se sustituyó por el real (paso 24) |
| 24 | `sales-forecast-evaluation.md` | Validación cruzada temporal, curva de aprendizaje, diagnóstico | ✅ (diagnóstico de sobreajuste; corrección propuesta no aplicada) |
| 25 | `rag-knowledge-base-fase1.md` | RAG completo, grafo del agente, tools y enrutamiento | 🔄 Tools HTTP ❌ eliminadas (paso 26); panel `/knowledge` → chat (paso 33); JWT (paso 34); prompt delimitado (paso 35) |
| 26 | `mcp-server-tools.md` | Servidor MCP con OAuth 2.1 y migración del agente | ✅ (falta la prueba manual en MCP Playground) |
| 27 | `agent-memory.md` | Memoria del agente en Redis con aprobación del usuario | ✅ (falta la sección "Decisiones de diseño", no recibida) |
| 28 | `agent-guardrails.md` | System prompt seguro, guardrails y auditoría | 🔄 ACL de pedidos movido al servidor (paso 34); normalización de texto (paso 35) |
| 29 | `rfp-intake-fase1.md` | Recepción de RFPs: PDF → clasificar → workers → síntesis | 🔄 Emite el evento en tiempo real al clasificar (paso 32) |
| 30 | `rfp-generation-evaluation-fase2.md` | Generación por departamento y 3 evaluadores en paralelo | ✅ |
| 31 | `rfp-approval-fase3.md` | Aprobación humana con `interrupt()`, arbitraje, documento final | ✅ (UI no recorrida en un navegador real) |
| 32 | `rfp-realtime-sse.md` | Notificación SSE de RFPs nuevas | ✅ |
| 33 | `cx-chat-websocket.md` | Chat por WebSocket con *streaming* e interrupción | 🔄 ACL de pedidos y rate limit añadidos (pasos 34-35) |
| 34 | `owasp-auditoria-hardening.md` | Auditoría OWASP Top 10, correcciones y endurecimiento del servidor | ✅ (riesgos residuales documentados) |
| 35 | `nist-seguridad-ia.md` | Inventario de IA, seguridad por diseño e informe NIST | ✅ (11 brechas documentadas) |

---

### 5b. Versión desarrollada

#### Paso 1 — Recuperación de contraseña

- **Qué se pidió y qué se hizo.** Tres flujos: "olvidé mi contraseña" (`POST /auth/forgot-password` envía un email con un enlace), "restablecer" (`POST /auth/reset-password` con un token de un solo uso) y "cambiar" estando logueado (`POST /auth/change-password`). Más sus tres pantallas en el backoffice (`/forgot-password`, `/reset-password`, `/account/change-password`).
- ⚠️ El documento es una **especificación con las casillas sin marcar**, pero el código existe: endpoints en `services/incidents-api/main.py`, tokens en `password_reset_service.py` (cada token tiene un `jti` y un campo `used`, así que no se puede usar dos veces) y email con Resend en `email_service.py`.
- **Por qué en ese momento.** Es la base de cualquier sistema con usuarios: sin recuperación de contraseña, un usuario bloqueado necesita a un administrador.
- **Archivos.** `services/incidents-api/{main.py, auth_service.py, password_reset_service.py, email_service.py}`; `uis/backoffice/src/app/{forgot-password, reset-password, (protected)/account/change-password}`.
- **Conceptos nuevos.** [JWT](#g-jwt), [hash](#g-hash), [variable de entorno](#g-env), token de un solo uso.
- **Conexiones.** El paso 18 refactoriza estos formularios con el hook `useApiSubmit`. El paso 34 cambia el almacenamiento de contraseñas a [scrypt](#g-scrypt).
- **Detalle de seguridad para la defensa.** `forgot-password` siempre responde lo mismo ("Si esa dirección está registrada, recibirás un enlace…"), exista o no el email. Así nadie puede averiguar qué emails tienen cuenta.

#### Paso 2 — Gestor de incidencias

- **Qué se pidió.** Un sistema de "tickets" operativos: modelo con categoría, estado (`open → in_progress → resolved/discarded`), origen (`customer/branch/internal`) y sede (`la_warehouse`, `zaragoza_office`…). Además: seed idempotente desde un CSV histórico, 5 endpoints (`/api/incidents`, `/{id}`, `/{id}/status`, `/summary`) y dos paneles en el backoffice.
- **Qué se hizo.** El modelo, los endpoints con validación de transiciones (`INCIDENT_STATUS_TRANSITIONS` en `models.py`), el seed (`scripts/seed_incidents.py`, idempotente por `source_incident_id`) y el panel (`incidents-management-panel.tsx`).
- ⚠️ **A medias:**
  1. `VALID_INCIDENT_CATEGORIES` solo tiene **3 de las 9** categorías (`lost_parcel`, `carrier_issue`, `inventory_discrepancy`). El propio paso avisaba de que faltaban 6 y nunca se completaron.
  2. El seed reutiliza la validación de `incident_analysis.py` (en la raíz), **no** de `packages/shared/` como pedía la especificación.
  3. Las incidencias se guardan en **TinyDB**, no en PostgreSQL.
- **Archivos.** `services/incidents-api/{models.py, main.py}`, `scripts/seed_incidents.py`, `uis/backoffice/src/components/incidents-management-panel.tsx`.
- **Conceptos nuevos.** [Máquina de estados](#g-maquina-estados), [idempotencia](#g-idempotencia), [seed](#g-seed), [endpoint](#g-endpoint), códigos HTTP 400/404/500.
- **Conexiones.** El paso 9 optimiza su tabla con `useMemo`. Las incidencias se convierten en una **tool** del agente en los pasos 25-26.

#### Paso 3 — Gestión de errores

- **Qué se hizo.** Endurecer el manejo de errores en todo el código:
  - **Frontend**: patrón de tres estados (cargando / éxito / error con botón "Reintentar"), `try/catch` en cada `fetch`, mensajes legibles en lugar de `SyntaxError: Unexpected token`, y `finally` para quitar siempre el *spinner*.
  - **Backend**: un manejador global que devuelve 500 sin *stack trace*, y 400 con el campo problemático.
  - **Scripts**: errores a `stderr` y `sys.exit(1)`.
- **Por qué.** Un error crudo asusta al usuario y puede filtrar información interna (rutas, conexiones).
- **Archivos.** `uis/backoffice/src/lib/auth-context.tsx` y `api-errors.ts`, varios paneles, `email_service.py`, `scripts/seed_incidents.py`, `analyze.py`.
- **Conceptos nuevos.** [try/catch](#g-trycatch), *optional chaining* (`?.`), [stderr](#g-stderr), [stack trace](#g-stacktrace).
- **Conexiones.** Este patrón de errores lo reutilizan todos los paneles posteriores (inventario, RFP, chat).

#### Paso 4 — Integración con la API de inventario

- **Qué se hizo.** Un único módulo (`uis/backoffice/src/lib/inventory.ts`) con todas las llamadas a `/inventory`. Ofrece `createInventoryApi(authFetch)` y una clase `InventoryApiError` que guarda el código HTTP y un mensaje legible.
- **Por qué.** Si cada pantalla hiciera su propio `fetch`, cambiar una URL o el manejo de errores obligaría a tocar 6 sitios.
- **Conceptos nuevos.** [Capa de integración](#g-capa), inyección de dependencias (se le "pasa" `authFetch`).
- **Conexiones.** Lo consumen los pasos 5 y 6.

#### Paso 5 — Inventario: productos y órdenes de entrada

- **Qué se hizo.** Página `/inventory/products` con el stock actual por producto, avisos de stock bajo (≤ 10 unidades, constante `LOW_STOCK_THRESHOLD`) y un formulario de entrada de mercancía (`/inventory/orders/inbound`) que permite elegir el producto por nombre.
- **Concepto de negocio clave.** El stock **nunca se guarda**: se **calcula** cada vez como suma de entradas menos suma de salidas (`techContext.md`, "Stock calculado, nunca almacenado"). Ver el código en la sección 10.
- **Conceptos nuevos.** Stock derivado, [SKU](#g-sku).
- **Conexiones.** Los eventos `inbound_order_created` de este formulario se convierten en telemetría (paso 15).

#### Paso 6 — Orden de salida e historial

- **Qué se hizo.** Formulario de salida (`/inventory/orders/outbound`) que muestra el stock disponible y avisa **antes de enviar** si la cantidad lo supera. Si aun así se envía, el backend responde 400 ("Insufficient stock…") y el mensaje aparece junto al campo. Más un historial de movimientos de solo lectura (`/inventory/orders`).
- **Por qué validar dos veces** (navegador y servidor). El aviso del navegador es comodidad; la regla real la impone el servidor, que es el único en el que se puede confiar.
- **Conceptos nuevos.** Validación en cliente frente a validación en servidor.

#### Paso 7 — Protección de rutas de inventario

- **Qué se hizo.** Comprobar que las 4 páginas de inventario están dentro de `app/(protected)/`, cuyo `layout.tsx` usa `auth-guard.tsx`: sin sesión, redirige a `/login`.
- ⚠️ **Para la defensa.** El *guard* del navegador es solo de **experiencia de usuario**: cualquiera podría llamar a la API directamente. La protección real tiene que estar en el servidor. Las **lecturas** de inventario (`GET /inventory/products` y `/orders`) **no exigían JWT** hasta el paso 34, que lo corrigió (hallazgo C3).
- **Conceptos nuevos.** Ruta protegida, [guard](#g-guard).

#### Paso 8 — Docker Compose full-stack

- **Qué se hizo.** Dockerfiles para los frontends (`uis/Dockerfile`, Node 20) y el backend (`services/Dockerfile`, Python 3.12), un `docker-compose.yml` con red interna `trackflow_network` y un `Makefile` con atajos (`make up`, `make health`…).
- 🔄 **Cambió después.** El compose actual tiene **8 servicios**: los 2 originales (`uis`, `backend`) más `worker`, `redis` y `flower` (paso 22), `reporting` (paso 20), y `qdrant` y `knowledge-api` (paso 25). En el paso 34, Redis, Flower y Qdrant quedaron ligados a `127.0.0.1`. El servidor MCP **no** está en el compose.
- **Conceptos nuevos.** [Contenedor](#g-contenedor), [imagen](#g-imagen), red Docker, *hot reload*, [Makefile](#g-makefile).

#### Paso 9 — `useMemo` en el panel de incidencias

- **Qué se hizo.** En `incidents-management-panel.tsx`, las filas de la tabla se precalculan una vez con `useMemo`: se usa un `Set` para saber qué incidencias se están actualizando (búsqueda instantánea, O(1)) y se crea el formateador de fechas una sola vez.
- **Analogía.** En vez de volver a calcular la cuenta del restaurante cada vez que alguien mira la mesa, la guardas en un papel y solo la rehaces si cambia lo pedido.
- **Conceptos nuevos.** [useMemo](#g-usememo), [renderizado](#g-render), complejidad O(1).

#### Paso 10 — Registro de órdenes

- Documento índice de la sesión del 10 de agosto: 9 solicitudes (lazy loading, useMemo, análisis de endpoints, caché), todas marcadas como completadas, con enlace a sus artefactos. No añade código; sirve de mapa de los pasos 9 a 14.

#### Paso 11 — Lazy loading en la web corporativa

- **Qué se hizo.** Identificar dos componentes pesados que se pueden cargar después (`LandingInteractions`, con animaciones y carrusel, y `QuoteForm`, el formulario de presupuesto) y cargarlos con `next/dynamic`. Verificado en `uis/website/src/app/page.tsx` y `application/page.tsx`.
- **Por qué.** El texto principal se ve antes; el JavaScript interactivo llega después sin bloquear.
- **Conceptos nuevos.** [Lazy loading](#g-lazy), hidratación, SEO.

#### Paso 12 — Análisis de endpoints por coste y frecuencia

- **Qué se hizo.** Una tabla de **todos** los endpoints de incidents-api con su coste, su frecuencia de uso y la frecuencia de cambio de sus datos. Conclusión: `POST /api/incidents/analyze` es el único de coste "muy alto" (lee y valida un CSV entero).
- **Por qué importa.** Este análisis justifica decisiones posteriores: qué cachear (pasos 13-14) y qué mover a segundo plano con Celery (paso 22).
- **Conceptos nuevos.** Coste de un endpoint, patrón N+1, complejidad O(n).

#### Paso 13 — Implementación de caché

- **Qué se hizo.** Caché en memoria con [TTL](#g-ttl) para `GET /suppliers` (45 s, clave = filtros) y `GET /auth/me` (20 s, clave = token), con candados (`RLock`) por concurrencia e **invalidación** al escribir (crear o borrar un proveedor vacía la caché de proveedores; cambiar la contraseña invalida la de ese usuario). Código en `main.py` (`SUPPLIERS_CACHE`, `AUTH_ME_CACHE`).
- **Conceptos nuevos.** [Caché](#g-cache), TTL, invalidación, *lock*.

#### Paso 14 — Candidatos a caché

- Justificación de por qué esos dos endpoints: coste medio-alto, llamadas muy frecuentes y datos que cambian poco. Y por qué **no** cachear inventario ni el resumen de incidencias: sus datos cambian a cada movimiento y mostrar stock antiguo sería peligroso.

#### Paso 15 — Telemetría: captura en el frontend

- **Qué se hizo.**
  - **Backend**: `POST /telemetry/events` con un modelo estricto de evento (`eventId`, `timestamp`, `sessionId`, `userId`, `event_type`, `schemaVersion`, `requestId`, `properties`).
  - **Frontend**: `services/telemetry.ts` mantiene una cola en memoria y envía por lotes (cada 10 s o cada 20 eventos), con reintentos y `sendBeacon` al cerrar la pestaña.
  - **Instrumentación**: 13 de los 15 eventos del plan, como login, `route_changed`, `inbound_order_created`, `api_latency_recorded` o `frontend_error_captured`.
- ⚠️ **Dos eventos sin cablear** (`direct_stock_edit_rejected`, `inventory_discrepancy_detected`): no existe la funcionalidad que los dispararía. Se decidió no inventar datos.
- **Conceptos nuevos.** [Telemetría](#g-telemetria), [evento](#g-evento), *batching*, *beacon*, [CORS](#g-cors).
- **Conexiones.** Los eventos se guardan en el paso 16, se analizan en el 17 y alimentan el pipeline de KPIs del 20.

#### Paso 16 — Telemetría: almacenamiento en Supabase

- **Qué se hizo.**
  - **Tabla `telemetry_events`**: clave primaria `event_id` e índices en `timestamp`, `event_type` y [GIN](#g-gin) sobre `properties` ([JSONB](#g-jsonb)). La tabla es **inmutable**: solo inserciones.
  - **Endpoint real**: valida cada evento por separado. Si en un lote de 5 hay 3 malos, guarda los 2 buenos y responde `{"received":5,"stored":2,"rejected":3}`.
  - **Inserción**: se hace en bloque (*bulk insert*).
- **Hallazgo de seguridad.** `services/incidents-api/.env` estaba **subido a git** con el secreto JWT y la conexión de Supabase. Se sacó del control de versiones y se añadió `.env` al `.gitignore`.
- **Conceptos nuevos.** [Índice](#g-indice), JSONB, *bulk insert*, rechazo parcial, [clave primaria](#g-pk).

#### Paso 17 — Pipeline de análisis y endpoint de informe

- **Qué se hizo.** `services/incidents-api/telemetry/analysis.py` con 4 métricas técnicas calculadas con pandas, sin bucles: **volumen**, **tasa de errores**, **latencia** (p50/p95/p99) y **disponibilidad** (% de respuestas no-5xx). Se exponen en `GET /telemetry/report?start_date&end_date`; por defecto, los últimos 7 días.
- **Bloqueo.** El proyecto gratuito de Supabase se **pausó** por inactividad, así que se verificó con un PostgreSQL local en Docker.
- 🔄 **Cambió después.** Desde el paso 34 el informe exige JWT. La caché prevista como "siguiente paso" nunca se implementó.
- **Conceptos nuevos.** [Percentil](#g-percentil) (p95), latencia, disponibilidad, función pura.
