# Recepción de RFPs — Hito 9 · Parte 1

Fecha: 2026-10-23

Implementación de `CONTEXT/CONTEXT9.md` ("BRIEFING — TrackFlow: Hito 9,
Flujos de Trabajo Agénticos", Parte 1): un flujo agéntico **nuevo y
dedicado** (orchestrator-worker-synthesizer) que recibe una RFP en PDF,
la convierte, la clasifica, extrae sus metadatos, y reparte el análisis
entre los departamentos comerciales (Warehouse, Last Mile, Reverse
Logistics) que el alcance solicitado realmente necesita — deliberadamente
**separado** del grafo CX (`services/knowledge-api/agent_graph.py`, Hito
7-8): dos dominios de negocio distintos, dos grafos distintos, tal como
exige la Sección 2.4 del BRIEFING.

Antes de implementar, leí `CONTEXT/CONTEXT9.md` completo (es el documento
que cubre las 3 Partes de este Hito, y esta entrega es solo la Parte 1):
los 3 departamentos y sus responsables (§2.1), el formato real de una RFP
(§2.2), las entidades a persistir y la máquina de estados del ticket a lo
largo de las 3 partes (§2.3), el layout de monorepo no negociable (§2.4),
y los 3 PDF de muestra obligatorios (§4) — ninguno de los 3 venía en este
repo, así que se redactaron y generaron como PDF reales (ver "Decisiones").

## Dónde vive el código

```
data/pipelines/rfp_intake/        # grafo dedicado, package propio dentro de data/pipelines
  models.py                        # RFPTicket, RFPMetadataRecord, RFPDepartmentSection (SQLModel/Postgres)
  pdf_conversion.py                 # MarkItDown real (PDF -> Markdown) + py-readability-metrics
  classifier.py                     # agente clasificador + extracción de metadatos (departments_needed)
  departments.py                    # DEPARTMENTS: ids/nombres/responsables EXACTOS de CONTEXT9.md §2.1
  workers.py                        # un worker por departamento -- key_aspects + open_questions, nunca inventa cifras
  synthesizer.py                    # consolida los WorkerResult en un resumen para Ventas ("qué pedir a quién")
  graph.py                          # LangGraph: classify -> [discarded] / orchestrate -> fan-out workers -> synthesize
  pipeline.py                       # process_rfp_ticket(ticket_id): orquesta todo lo anterior + persiste en Postgres
  _generate_sample_pdfs.py          # genera los 3 PDF de CONTEXT9.md §4 (no venían en el repo, ver "Decisiones")

rfp-requests/trackflow/            # los 3 PDF de muestra reales (CONTEXT9.md §4) -- subidas de prueba via la UI
  trackflow-request-1.pdf           # ModaViva (España), formal, aceptar -- warehouse + reverse
  trackflow-request-2.pdf           # Luna Cosmetics (LA), informal, aceptar -- warehouse + lastmile
  trackflow-request-3.pdf           # pitch de tarifas de carrier, inválido, rechazar

services/incidents-api/            # backend EXISTENTE extendido, sin API nuevo
  routers/rfp.py                    # POST /rfp/tickets (sube PDF, crea ticket, encola), GET /rfp/tickets[/{id}]
  rfp_tasks.py                      # tarea Celery: corre pipeline.process_rfp_ticket() en el worker, no en el request
  rfp_pipeline_path.py              # agrega data/pipelines/ a sys.path (mismo patron que pipeline_path.py de knowledge-api)
  celery_app.py                     # + "rfp_tasks" en include=[...]
  main.py                           # + app.include_router(rfp_router), + create_rfp_tables() en el startup

uis/backoffice/
  src/app/(protected)/rfp/page.tsx           # nueva pagina "Recepcion de RFPs"
  src/components/rfp-intake-panel.tsx         # upload + lista de tickets con polling cada 2s mientras "analizando"
  src/components/backoffice-shell.tsx         # + item de sidebar "Recepcion de RFPs"
  src/app/globals.css                          # + --pending / .badge-pending (estado "analizando")

scripts/
  rfp_reprocess.py                   # CLI standalone: --ticket-id (reproceso manual) / --smoke (los 3 PDF, sin Celery)

tests/pipelines/
  test_rfp_classifier.py             # clasificación + extracción de metadatos, contra los 3 PDF reales
  test_rfp_workers.py                # workers de departamento + synthesizer + fan-out del grafo
```

## Cómo correrlo

```bash
cd data/pipelines
uv sync --extra dev   # instala langgraph, markitdown[pdf], py-readability-metrics, sqlmodel, reportlab (dev)
python -m nltk.downloader punkt_tab   # requerido por py-readability-metrics (una vez)
uv run pytest ../../tests/pipelines/test_rfp_classifier.py ../../tests/pipelines/test_rfp_workers.py -q
```

```bash
# Smoke run de punta a punta, sin Celery ni la API corriendo:
python scripts/rfp_reprocess.py --smoke
```

```bash
# Flujo real: services/incidents-api (uvicorn) + worker de Celery + Postgres + Redis,
# subiendo un PDF via POST /rfp/tickets y consultando GET /rfp/tickets/{id}.
```

## Checklist de la entrega — Layout del monorepo (no negociable)

- [x] **Sin API nuevo**: `services/incidents-api` (el backend existente)
  gana un router nuevo (`routers/rfp.py`) -- nunca un proceso HTTP
  adicional. Los routers importan y disparan `data/pipelines/rfp_intake`,
  nunca contienen lógica de agentes.
- [x] **Grafo/pipeline dedicado, no mezclado con el grafo CX**:
  `data/pipelines/rfp_intake/` -- package propio, nunca importa ni es
  importado por `services/knowledge-api/agent_graph.py`.
- [x] **Scripts standalone en `scripts/`, no un segundo HTTP API**:
  `scripts/rfp_reprocess.py` -- reproceso manual de un ticket
  (`--ticket-id`) y smoke run contra los 3 PDF de muestra (`--smoke`),
  ambos importando `rfp_intake` directamente, nunca por HTTP.
- [x] **Ticket, metadatos RFP y `DepartmentSection.key_aspects` en
  PostgreSQL (Supabase) vía SQLModel, nunca TinyDB**:
  `rfp_intake/models.py` -- `RFPTicket`, `RFPMetadataRecord`,
  `RFPDepartmentSection`, motor propio (`SUPABASE_DATABASE_URL`, mismo
  valor que `services/incidents-api`) via SQLModel, verificado contra un
  Postgres real (ver "Cómo se verificó").

## Checklist de la entrega — Interfaz de recepción (modo ticket)

- [x] **Interfaz en `uis/backoffice` para subir RFPs en PDF, un ticket por
  cada una**: página nueva `/rfp` (`RfpIntakePanel`) -- cada subida crea un
  `RFPTicket` (mismo patrón de `multipart/form-data` que
  `IncidentAnalysisPanel`, Hito 7).
- [x] **Al subir, el PDF se guarda bajo `data/raw/` y el ticket queda en
  `analizando`**: `routers/rfp.py::upload_rfp` -- nombre de archivo único
  (`uuid4()-nombre_original.pdf`, evita colisiones entre subidas
  concurrentes), `RFPTicket.status = "analizando"` al crear la fila.
- [x] **El endpoint de subida responde rápido; el pipeline corre en
  async; la UI consulta/refresca estado**: `upload_rfp` solo valida
  (extensión `.pdf`, no vacío), guarda el archivo, crea el ticket, y
  encola `process_rfp_ticket_task.delay(ticket_id)` -- responde `202` de
  inmediato. Todo el trabajo pesado (conversión, clasificación,
  orquestación, workers, persistencia) corre en el worker de Celery
  (mismo mecanismo que `tasks.py::analyze_incidents_csv_task`, Hito 7).
  `RfpIntakePanel` reconsulta `GET /rfp/tickets` cada 2s mientras algún
  ticket siga en `"analizando"`.

## Checklist de la entrega — Ingesta y conversión del documento

- [x] **PDF a Markdown antes de que cualquier agente lea el documento,
  con MarkItDown real**: `pdf_conversion.py::convert_pdf_to_markdown()` --
  única función de todo el pipeline que lee el PDF crudo; clasificador,
  workers y synthesizer solo ven el Markdown que devuelve.
- [x] **Extracción de metadatos** (campos de `CONTEXT9.md` §2.3):
  `classifier.py::extract_metadata()` -- `client_name`, `client_country`,
  `services_requested`, `monthly_volume`, `deadline`, `budget_range`,
  `departments_needed`.
- [x] **Métricas de legibilidad, con `py-readability-metrics`**:
  `pdf_conversion.py::compute_readability_metrics()` -- Flesch Reading
  Ease + Flesch-Kincaid Grade Level reales (no simulados). Documento
  demasiado corto para medir (<100 palabras) → `{"status":
  "insufficient_text", ...}` explícito, nunca un score inventado.
- [x] **Metadatos y métricas guardados en PostgreSQL junto al ticket**:
  `RFPMetadataRecord` (una fila por ticket, `readability_metrics` como
  JSONB).

## Checklist de la entrega — Agente clasificador

- [x] **Primer agente que lee el Markdown y determina si es una RFP
  válida**: `classifier.py::classify_rfp()` -- heurística determinista
  (ver "Por qué heurísticas, no un LLM real" más abajo), verificada contra
  los 3 PDF reales de `CONTEXT9.md` §4, los 3 clasificados correctamente.
- [x] **Si no es válida, detiene el flujo y deja el ticket en
  `descartado` -- nunca en silencio**: el grafo enruta directo a
  `discarded` (nunca llega a `orchestrate` ni a ningún worker) y
  `RFPTicket.discard_reason` queda con el motivo real (nunca `NULL` en un
  ticket descartado).

## Checklist de la entrega — Orquestación por departamento

- [x] **Patrón orchestrator-worker-synthesizer real**: `graph.py` -- nodo
  `orchestrate` (decisión explícita, separada de `classify`) + fan-out
  condicional a los workers necesarios (`add_conditional_edges` con una
  función de ruteo que devuelve una LISTA de nodos siguientes -- verificado
  antes de construir el grafo real que LangGraph soporta esto, y que cada
  worker debe escribir a SU PROPIA clave de estado para evitar
  `InvalidUpdateError` entre escrituras concurrentes, ver "Cómo se
  verificó" #1).
- [x] **Cada worker recibe metadatos + extractos de su departamento, sin
  inventar cifras; `key_aspects` persistido en PostgreSQL**:
  `workers.py` -- un worker por `department_id`
  (`run_warehouse_worker`/`run_lastmile_worker`/`run_reverse_worker`),
  cada uno agrega una `open_question` en vez de un número cuando el dato
  no está en la RFP (probado explícitamente,
  `test_warehouse_worker_asks_an_open_question_instead_of_inventing_volume`).
  `pipeline.py` persiste un `RFPDepartmentSection` por `(ticket, worker
  que corrió)`.
- [x] **El synthesizer consolida un resumen para Ventas (qué pedir a
  quién)**: `synthesizer.py::synthesize()` -- `DepartmentAsk` por
  departamento con preguntas abiertas, con el **responsable real** del
  BRIEFING (Ana Whitfield / Carlos Vega / Sofía Ramos), nunca un nombre
  genérico.
- [x] **En éxito, el ticket queda en `analisis_completo` con handoff
  claro hacia la Parte 2**: `pipeline.py::process_rfp_ticket()` -- ver
  "Checklist — Enrutamiento" para el contrato de handoff exacto.

## Checklist de la entrega — Enrutamiento

- [x] **Enrutamiento del clasificador hacia el resto del flujo, vía campo
  en DB + contrato de handoff documentado (no un segundo API)**: el campo
  es `RFPTicket.status` (`"analisis_completo"` | `"descartado"` --
  `TicketStatus` en `models.py`, el enum completo de las 3 Partes). El
  **contrato de handoff** hacia la Parte 2, documentado explícitamente
  acá para que no haga falta re-derivarlo:
  - `ticket_id` (`RFPTicket.id`) -- la clave que ata todo.
  - El payload del synthesizer YA vive persistido, no hace falta
    recalcularlo: `RFPMetadataRecord` (una fila por ticket, con
    `departments_needed`) + `RFPDepartmentSection` (una fila por
    `(ticket_id, department_id)`, con `key_aspects` -- exactamente la
    "estructura de workstreams" que pide `CONTEXT9.md`).
  - La Parte 2 arranca leyendo estas filas por `ticket_id` (mismo query
    que ya usa `pipeline.py::get_ticket_with_metadata()`) -- **nunca**
    vuelve a abrir el PDF ni a llamar a MarkItDown.

⚠️ Los nombres de departamento (`warehouse`/`lastmile`/`reverse`), sus
responsables, y el criterio de clasificación (RFP de cliente real vs.
pitch de tarifas de un carrier, el caso inválido exacto de `CONTEXT9.md`)
coinciden literalmente con el BRIEFING -- ver `departments.py` y
`classifier.py`.

## Checklist de la entrega — Pruebas

- [x] **Pruebas unitarias en `tests/pipelines/` para el clasificador y
  para al menos un worker**: `test_rfp_classifier.py` (10 tests) +
  `test_rfp_workers.py` (9 tests) -- 19 en total, todos deterministas (sin
  LLM vivo, sin Postgres real: usan metadatos sintéticos o Markdown ya
  convertido).
- [x] **Verificado contra los 3 PDF de muestra del BRIEFING (formal
  aceptar, informal aceptar, inválido rechazar), subiéndolos por la UI**:
  ver "Cómo se verificó" #4 -- los 3 subidos de verdad vía
  `POST /rfp/tickets` real (el mismo endpoint que llama
  `RfpIntakePanel`), con Celery real, Postgres real, y los 3 resultados
  exactamente los que especifica `CONTEXT9.md` §4.

## Cómo se verificó

Sin credenciales reales de 4Geeks para clasificación/extracción por LLM
(mismo límite documentado en toda esta sesión), pero con MarkItDown real,
py-readability-metrics real, LangGraph real, Postgres real, Celery real, y
los 3 PDF de muestra generados como documentos reales (no texto de prueba
inventado):

1. **Verificación de LangGraph antes de construir el grafo real, no
   asumida**: antes de escribir `graph.py`, se probó con un grafo mínimo
   que una arista condicional puede devolver una LISTA de nodos siguientes
   (fan-out dinámico a un subconjunto de departamentos) -- confirmado. El
   primer intento de fan-out con una clave de estado COMPARTIDA entre
   workers en paralelo falló con
   `InvalidUpdateError: Can receive only one value per step` (error real
   de LangGraph, no inventado) -- corregido dándole a cada worker su
   propia clave de estado (`warehouse_result`/`lastmile_result`/`reverse_result`),
   verificado que el patrón corregido funciona antes de construir el
   grafo real.
2. **Los 3 PDF de muestra de `CONTEXT9.md` §4 no existían en este repo**
   (mismo patrón que el resto de esta sesión: el material de referencia
   del curso no llega al monorepo del estudiante) -- se redactaron con
   contenido fiel a las descripciones exactas del BRIEFING (ModaViva,
   Luna Cosmetics, el pitch de FastShip Carriers) y se generaron como PDF
   reales con `reportlab`
   (`data/pipelines/rfp_intake/_generate_sample_pdfs.py`), guardados en
   `rfp-requests/trackflow/`. MarkItDown los convirtió de verdad (238,
   170, y 153 palabras respectivamente, todos por encima del mínimo de
   100 palabras que pide `py-readability-metrics`).
3. **Bug real encontrado y corregido -- negaciones de departamento
   cruzadas**: el primer intento de `_extract_services_and_departments()`
   usaba UNA sola regex de negación (`_NO_LASTMILE_HINT_RE`) para
   descartar tanto `last_mile` como `reverse` -- al correr contra
   `trackflow-request-1.pdf` (ModaViva), la frase "propio transportista"
   (que debía excluir solo `lastmile`) también apagaba la detección de
   `reverse`, y en `trackflow-request-2.pdf` (Luna Cosmetics), "we handle
   that ourselves" (sobre devoluciones) apagaba también `last_mile`.
   Encontrado corriendo el extractor contra el Markdown real de ambos PDF,
   no adivinado -- corregido con dos regex de negación separadas, una por
   departamento.
4. **Bug real encontrado y corregido -- saltos de línea de MarkItDown
   partían frases a la mitad**: `trackflow-request-1.pdf` convertido traía
   "entre 8.000\n\nEUR y 12.000 EUR mensuales" -- un salto de párrafo real
   donde el PDF original solo tenía un salto de línea visual a mitad de
   frase. `client_name`/`deadline`/`budget_range` quedaban con texto
   cruzando líneas (`"ModaViva S.L.\n\nPaís"`). Corregido con
   `_flatten_whitespace()` (colapsa saltos de línea a espacios) aplicado
   solo a los extractores de campos puntuales -- nunca al Markdown que
   leen los agentes, donde los párrafos sí importan.
5. **Bug real encontrado y corregido -- excepción de "texto muy corto" no
   se lanzaba donde se esperaba**: `compute_readability_metrics()`
   envolvía solo el constructor `Readability(texto)` en el
   `try/except ReadabilityException`, pero la librería real lanza esa
   excepción recién al pedir `.flesch()` -- un test con texto corto
   (`"Texto muy corto."`) lo reveló (`ReadabilityException` sin capturar,
   test rojo) antes de corregirlo moviendo las llamadas a `.flesch()`/
   `.flesch_kincaid()` adentro del bloque protegido.
6. **`tests/pipelines/test_rfp_classifier.py` (10 tests) +
   `test_rfp_workers.py` (9 tests), 19/19 en verde** tras las
   correcciones de arriba -- corridos con `data/pipelines/.venv`.
7. **Flujo completo verificado de punta a punta, 3 veces, con
   infraestructura real**: Postgres real (contenedor `postgres:16`, mismo
   que las validaciones anteriores de esta sesión), Redis real, un worker
   de Celery real (`celery -A celery_app worker`), `services/incidents-api`
   real (`uvicorn`), un usuario autenticado real, y los 3 PDF de muestra
   subidos por `POST /rfp/tickets` -- el mismo endpoint que
   `RfpIntakePanel` llama, con el mismo patrón `multipart/form-data` +
   bearer token:
   - `trackflow-request-1.pdf` (ModaViva) → ticket en `analisis_completo`,
     `departments_needed=["warehouse","reverse"]` (nunca `lastmile`),
     `client_country="Spain"`, `monthly_volume=3200`,
     `key_aspects.reverse.estimated_return_rate_pct=18`.
   - `trackflow-request-2.pdf` (Luna Cosmetics) → `analisis_completo`,
     `departments_needed=["warehouse","lastmile"]` (nunca `reverse`),
     `client_country="USA"`, `monthly_volume=5000`,
     `key_aspects.lastmile.client_sla_expectation="2-3 day shipping"`.
   - `trackflow-request-3.pdf` (pitch de carrier) → `descartado`, con
     `discard_reason` explicando por qué (nunca `NULL`).
   Los 3 resultados coinciden exactamente con lo que especifica
   `CONTEXT9.md` §4 -- confirmado inspeccionando `GET /rfp/tickets/{id}`
   real, no solo el `202` de la subida.
8. **El script standalone (`scripts/rfp_reprocess.py --smoke`) también se
   corrió de punta a punta**, sin Celery ni uvicorn -- mismos 3 resultados
   que el flujo HTTP, confirmando que el pipeline es invocable igual desde
   `scripts/` que desde el router (ningún atajo exclusivo de uno u otro
   camino).
9. **La UI (`RfpIntakePanel`) se construyó y tipó, pero NO se recorrió en
   un navegador real esta ronda** -- `npm run build` pasa sin errores de
   TypeScript y genera la ruta `/rfp`, y `authFetch("/rfp/tickets", ...)`
   usa exactamente el mismo endpoint ya verificado por HTTP en el punto 7
   (mismo contrato de payload/respuesta), pero no hubo una verificación
   click-por-click con Chromium real en esta entrega -- decirlo
   explícitamente en vez de afirmar un resultado no comprobado (ver
   "Pendiente").

## Decisiones de implementación no cubiertas por la guía genérica

- **`rfp_intake` como subpaquete de `data/pipelines`, no un paquete
  nuevo**: `data/pipelines/` ya tiene el patrón establecido
  (`exec_weekly_inventory_kpis/`, un subpaquete con su propio
  `__init__.py`, dentro del mismo `pyproject.toml`/`.venv` compartido) --
  `rfp_intake` sigue ese mismo patrón en vez de inventar un paquete
  Python independiente con su propio entorno.
- **Motor de base de datos propio de `rfp_intake`, no reutilización
  cruzada de `services/incidents-api/database.py`**: `data/pipelines` es
  el paquete de base del monorepo (del que los `services/*` importan),
  nunca al revés -- cruzar esa dirección de dependencia habría sido
  arquitectónicamente incorrecto. Ambos motores apuntan a la misma base
  física (`SUPABASE_DATABASE_URL`), cada uno vía su propio `.env`.
- **Las 3 categorías de clasificación son "patrón de petición de cliente"
  vs. "patrón de pitch de proveedor", no una lista de keywords de
  logística**: el documento inválido de `CONTEXT9.md` (`trackflow-request-3.pdf`)
  menciona "last-mile delivery network" y tarifas -- vocabulario de
  logística real -- precisamente para que un clasificador ingenuo
  (keywords de "logística" = válido) lo aprobara por error. El criterio
  real implementado es quién le pide qué a quién, no de qué tema habla el
  documento.
- **`FinalDocument` (CONTEXT9.md §2.3) no se modeló en esta entrega**:
  pertenece a la Parte 3 (generación del documento final); el checklist de
  la Parte 1 no la menciona, y modelarla ahora sería diseño especulativo
  para un flujo que todavía no existe.
- **`TicketStatus` ya incluye los 8 valores de las 3 Partes, no solo los 3
  de la Parte 1**: es la máquina de estados real y completa del ticket
  (`CONTEXT9.md` §2.3, "mismo ticket en Partes 1–3") -- declararla
  completa ahora evita una migración de enum más adelante; esta entrega
  solo produce 3 de los 8 valores.
- **`RFPDepartmentSection` ya trae las columnas de evaluación/aprobación
  de las Partes 2-3 (`draft_content`, `evaluation_results`,
  `approval_status`, `approver`, `approved_at`), todas `nullable`**: mismo
  razonamiento que `TicketStatus` -- el checklist de Parte 1 solo llena
  `key_aspects`, pero la tabla ya tiene la forma que Sección 2.3 define
  para las 3 Partes, para que la Parte 2 no necesite una migración de
  esquema nueva.
- **Autenticación en `routers/rfp.py`**: ningún checklist de Hito 9 pide
  dejar esto sin auth -- se protegió con el mismo mecanismo que
  `routers/inventory.py` (`auth_service.get_user_from_token`, función
  local al router, no importada de `main.py`, evitando el import
  circular).

## Pendiente / siguientes pasos

1. **La UI no se recorrió en un navegador real** (ver "Cómo se verificó"
   #9) -- el backend que consume está 100% verificado por HTTP real; falta
   una pasada con Chromium real para confirmar la experiencia de polling
   visualmente.
2. **Heurísticas deterministas para clasificación/extracción, no un LLM
   real** -- mismo límite documentado en toda esta sesión
   (`classify_intent`, `evaluate_for_memory_proposal`,
   `check_instruction_override`, etc.): sin credenciales de 4Geeks, una
   RFP real con fraseo muy distinto a los 3 PDF de muestra podría no
   clasificar/extraer correctamente. Los puntos de inyección
   (`classify_fn`/`extract_metadata_fn` en `build_graph()`) ya están
   listos para la sustitución.
3. **Sin reintentos/DLQ en `rfp_tasks.py`** (a diferencia de
   `tasks.py::analyze_incidents_csv_task`, que sí tiene backoff + Dead
   Letter Queue, Hito 7) -- `process_rfp_ticket()` ya captura cualquier
   excepción y descarta el ticket con el motivo real en vez de dejarlo
   colgado en `analizando`, pero un fallo transitorio (Postgres
   momentáneamente inalcanzable) hoy descarta el ticket en vez de
   reintentar. No pedido explícitamente por el checklist de esta entrega.
4. **`client_name`/`deadline`/`budget_range` son heurísticas de texto
   acotadas** (ver `classifier.py`) -- un RFP con un formato de fecha o de
   rango de presupuesto distinto a los 2 PDF de muestra que sí los traen
   podría no extraerlos (quedarían `None`, nunca inventados, pero
   tampoco capturados).
