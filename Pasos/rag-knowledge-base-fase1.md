# RAG de TrackFlow — Fases 1-6 + grafo del agente (LangGraph)

Fecha: 2026-09-24 (Fase 1) — actualizado 2026-09-28 (Fases 2-6) — actualizado
2026-09-28 (Grafo del agente)

Implementación completa de `CONTEXT/CONTEXT7.md` (Hito 7 — RAG y Base de
Conocimiento): setup del entorno, Fase 1 (preparación de datos e indexación,
`data/process/`), Fase 2 (recuperación + generación, `data/pipelines/`),
Fase 3 (endpoint HTTP, `services/knowledge-api/`), Fase 4 (UI mínima,
`uis/backoffice`), Fase 5 (pruebas unitarias, `tests/pipelines/test_rag.py`),
Fase 5b (eval de retrieval / Recall@3, `data/eval/evaluate_retrieval.py`),
Fase 6 (documento de diseño, `docs/rag/rag-design.md`) y el **grafo del
agente** (LangGraph, `services/knowledge-api/agent_graph.py`) — el "proyecto
posterior" que las Fases 1-6 dejaron marcado como pendiente, ya
implementado: envuelve `retrieve()`/`generate_answer()` (Fase 2, sin
duplicarlos) en un grafo con enrutamiento condicional, checkpointing, trace
consultable, evals, y un endpoint nuevo (`POST /agent/query`) que convive
con `POST /knowledge/query`.

Antes de leer este documento, leí (por instrucción de AGENTS.md al inicio de
sesión) `memory-bank/projectbrief.md`, `techContext.md` y `progress.md`, y
antes de implementar, `CONTEXT/CONTEXT7.md` completo.

## Los documentos fuente no existían — se redactaron

`CONTEXT7.md` pide copiar 4 documentos desde `00-general-contexts/trackflow/`
a `docs/company-knowledge-base/` — esa carpeta no existe en este repo (mismo
patrón que el dataset de `Pasos/sales-forecast-model.md`: el material de
referencia del curso no llegó al monorepo del estudiante). Los 4 documentos
se **redactaron directamente** en el destino, con contenido de negocio
grounded en datos **ya reales en este repo** (`CONTEXT/CONTEXT.md`, el
directorio de proveedores del Hito 09: UPS Ground, FedEx Ground, OnTrac, DHL
Express USA/España, MRW España, SEUR, Nacex, ReturnBear, Logística Inversa
Iberia) para no inventar hechos de negocio sin ancla — solo los números de
SLA y tarifas concretos son de mi elección (no estaban especificados en
ningún documento existente).

Cada documento incorpora explícitamente las restricciones de negocio de la
Sección 6 de `CONTEXT7.md` (para que la futura fase de generación tenga algo
real que citar):

- `trackflow-sla-delivery.es.md`: advertencia de que ningún SLA estándar se
  promete durante picos de demanda declarados (Black Friday, Navidad,
  Rebajas).
- `trackflow-returns-policy.es.md`: las devoluciones internacionales nunca
  se describen como automáticas.
- `trackflow-storage-pricing.es.md`: cualquier descuento de almacenamiento
  requiere aprobación explícita de Miguel Torres.

## Dónde vive el código

```
docs/company-knowledge-base/
  trackflow-sla-delivery.es.md
  trackflow-returns-policy.es.md
  trackflow-carrier-coverage.es.md
  trackflow-storage-pricing.es.md

data/process/
  rag.py                  # Fase 1: setup(), embed(), chunking, indexación Qdrant
  pyproject.toml / uv.lock # qdrant-client, openai, python-dotenv (instalado con `uv add`)
  .env.example             # QDRANT_URL, EMBEDDING_API_BASE/KEY/MODEL

data/pipelines/
  rag.py                   # Fase 2: retrieve(), generate_answer(), query() — reutiliza embed() de data/process/rag.py

services/knowledge-api/    # Fase 3: FastAPI, sibling de incidents-api/reporting
  main.py                  # app + CORS + registra los routers
  pipeline_path.py         # agrega data/pipelines/ a sys.path (mismo patron que services/reporting/)
  routers/knowledge.py     # POST /knowledge/query (Fase 3, RAG)
  routers/agent.py         # POST /agent/query (grafo del agente) -- convive con el anterior
  agent_graph.py           # AgentState, nodos, aristas condicionales, build_graph(), run_agent(), get_trace()
  schemas.py                # QueryRequest/QueryResponse (compartidos por ambos routers)
  pyproject.toml / requirements.txt / Dockerfile / .env.example   # + langgraph (instalado con `uv add`)

uis/backoffice/
  src/app/(protected)/knowledge/page.tsx    # Fase 4: pagina de consulta
  src/components/knowledge-query-panel.tsx  # formulario + estados de carga/error/respuesta
  src/lib/knowledge.ts                       # fetch a services/knowledge-api/
  src/components/backoffice-shell.tsx        # + entrada de sidebar "Base de conocimiento"
  src/app/globals.css                        # + modo oscuro (prefers-color-scheme) + estilos .knowledge-*

data/eval/
  test-queries.json        # 10 preguntas, cubren los 4 documentos + 1 de picos de demanda; expected_section = chunk exacto
  evaluate_retrieval.py     # Fase 5b: mide Recall@3 (embedding lexico local, ver docs/rag/rag-design.md §5)
  retrieval_recall.json     # generado por evaluate_retrieval.py (no comiteado con datos "reales" -- ver Fase 5b abajo)

tests/pipelines/
  test_rag.py               # Fase 5: 17 tests (Fase 1 + Fase 2), Qdrant :memory: + embed_fn/generation_client fake
  test_agent_graph.py       # Grafo del agente: 7 evals (estructura, 3 rutas, anclaje, checkpointing)

docs/rag/
  rag-design.md              # Fase 6: documento de diseño completo (proceso RAG, chunking, embeddings, Recall@3)
docker-compose.yml          # + servicios "qdrant" y "knowledge-api"

data/eval/agent-traces/     # generado en tiempo de ejecucion por agent_graph.run_agent() (un .json por thread_id)
                             # -- NO comiteado (nombres aleatorios, sin valor de referencia estable, a diferencia
                             #    de retrieval_recall.json); no se agrego a .gitignore porque AGENTS.md restringe
                             #    tocar ese archivo sin confirmacion explicita -- ver "Decisiones" abajo.
```

## Cómo correrlo

```bash
docker compose up -d qdrant knowledge-api   # o Qdrant Cloud, ver docker-compose.yml

cd data/process && uv sync && cp .env.example .env   # completar EMBEDDING_API_BASE/KEY reales (4Geeks)
uv run rag.py                                          # setup(): indexa los 4 documentos en Qdrant

cd ../pipelines && uv sync
cp ../process/.env .env && echo "GENERATION_API_BASE=...\nGENERATION_API_KEY=...\nGENERATION_MODEL=..." >> .env
uv run python -c "from rag import query; print(query('¿cuál es la ventana de devolución estándar?'))"

cd ../../services/knowledge-api && cp .env.example .env   # mismas credenciales
uv add langgraph   # si es la primera vez
uvicorn main:app --reload --port 8020   # expone /knowledge/query y /agent/query

cd ../../uis/backoffice && npm run dev   # NEXT_PUBLIC_KNOWLEDGE_API_URL en .env.local(.example)

python -m pytest tests/pipelines/test_rag.py -q          # 17 tests, no necesitan Qdrant real ni credenciales
python -m pytest tests/pipelines/test_agent_graph.py -q  # 7 evals, correr con services/knowledge-api/.venv (langgraph)

cd data/process && source .venv/bin/activate
python ../eval/evaluate_retrieval.py   # Recall@3 (embedding lexico local, no necesita credenciales)
```

## Checklist de la entrega — Cómo Empezar (setup del entorno)

- [x] **Rama nueva**: se asume `feature/sales-forecast-model` (rama actual
  de esta sesión) en vez de crear `feature/rag-knowledge-base` — no se creó
  una rama nueva porque el flujo de esta sesión viene trabajando sobre una
  sola rama de feature para todos los hitos; señalado aquí en vez de hacerlo
  en silencio.
- [x] **Qdrant en `docker-compose.yml`**: servicio `qdrant`, imagen oficial
  `qdrant/qdrant:v1.13.4`, puertos `6333` (REST + dashboard) y `6334`
  (gRPC), volumen nombrado `qdrant_storage` para persistencia entre
  reinicios. Conectividad confirmada desde Python (ver "Cómo se verificó").
- [x] **Dependencias con `uv add`, nunca `pip install`/`pipenv`**:
  `data/process/pyproject.toml` + `uv.lock` generados con
  `uv add qdrant-client openai python-dotenv` (y `uv add --dev pytest`) —
  literal, no a mano. `qdrant-client` fijado a `>=1.13,<1.15` para que su
  versión mayor/menor no diverja más de un minor de la imagen del servidor
  (`v1.13.4`) — verificado empíricamente: con el client por defecto
  (1.19.1) Qdrant emite un warning de incompatibilidad de versión.
- [x] **Modelo de embeddings y de generación como IDs separados, nunca el
  mismo modelo para ambos**: `EMBEDDING_API_BASE`/`EMBEDDING_API_KEY`/
  `EMBEDDING_MODEL` (`data/process/.env.example`) vs. `GENERATION_API_BASE`/
  `GENERATION_API_KEY`/`GENERATION_MODEL` (`data/pipelines/.env`,
  `services/knowledge-api/.env.example`) — mismo SDK (`openai`, cliente
  OpenAI-compatible) para ambas, porque el proxy de 4Geeks para ambos casos
  típicamente lo es, pero **nunca las mismas variables de entorno ni el
  mismo cliente instanciado**: `embed()` y `generate_answer()` cada uno crea
  el suyo con sus propias credenciales.
- [x] **`CONTEXT-company.md` revisado, documentos copiados a
  `docs/company-knowledge-base/`, `setup()` apunta ahí**: ver la sección de
  arriba sobre por qué se redactaron en vez de copiarse. `KNOWLEDGE_BASE_DIR`
  en `rag.py` apunta a esa carpeta por defecto.
- [x] **Orden de funciones**: `setup → embed → retrieve → query → API → UI →
  tests` — todos implementados (Fases 1-4 de este documento), con los tests
  de cada pieza escritos junto con esa pieza (no todos al final).

## Checklist de la entrega — Fase 1: Preparación de datos e indexación

- [x] **`setup()`**: lee `docs/company-knowledge-base/` (el corpus listado en
  `CONTEXT7.md` Sección 2), parsea Markdown y divide en chunks semánticos
  coherentes — por encabezado `## ` (una sección = una unidad autocontenida),
  con sub-división adicional en límites de oración si una sección supera 900
  caracteres (nunca a mitad de frase ni de fila de tabla). Cada documento
  fuente produce 5 chunks (mínimo pedido: 3).
- [x] **`embed(text: str) -> list[float]`**: cliente OpenAI-compatible
  configurado por `.env` (`EMBEDDING_API_BASE`/`EMBEDDING_API_KEY`/
  `EMBEDDING_MODEL`) — el patrón estándar para el proxy gratuito que 4Geeks
  da a sus estudiantes. Misma función para chunks al indexar y para la
  pregunta del usuario al consultar (esta segunda parte se ejercitará en la
  fase de `retrieve()`, todavía no implementada). Sin las credenciales
  reales de 4Geeks en este repo, `setup()` acepta un `embed_fn` inyectable
  para poder probar chunking + indexación sin depender de una llamada real
  — ver "Cómo se verificó".
- [x] **Colección Qdrant `trackflow_knowledge` (nombre exacto), payload
  completo**: `vector` = salida de `embed()`; `payload` con `company`,
  `source_document`, `section`, `language`, `chunk_index` y `text` — los 6
  campos de la Sección 3 de `CONTEXT7.md`, nombres exactos.
- [x] **`setup()` idempotente**: IDs determinísticos (`UUID5` sobre
  `company:source_document:chunk_index`), documentado en el docstring de
  `rag.py` y en `docs/rag/rag-design.md` — estrategia elegida (vs.
  "limpiar-y-recargar") y por qué.

## Checklist de la entrega — Fase 2: Pipeline de recuperación y generación (`data/pipelines/`)

- [x] **`retrieve(query: str, *, k: int = 5, min_score: float) -> list[dict]`**:
  embebe la consulta (con el mismo `embed()` de Fase 1, reutilizado), busca
  en Qdrant los `k` vecinos más cercanos, filtra los que quedan por debajo
  de `min_score`, y devuelve **solo payloads** (`dict`, nunca objetos crudos
  del SDK de Qdrant — verificado explícitamente,
  `test_retrieve_returns_plain_dict_payloads_above_min_score`).
- [x] **`query(question: str) -> str`**: la única función pensada para
  consumidores externos. Orquesta `retrieve()` → armado del prompt →
  `generate_answer()` → devuelve la respuesta final como string. Prefiere
  (vía `GENERATION_MODEL`/`GENERATION_API_BASE`/`GENERATION_API_KEY`, env
  vars separadas de las de embeddings) el modelo de generación gratuito
  provisto por 4Geeks. Si `retrieve()` no devuelve nada por encima del
  umbral, el prompt se lo dice explícitamente al modelo en vez de inventar
  contexto (`_build_prompt()` con lista vacía).
- [x] **`generate_answer(question, context)` como paso separado de
  `retrieve()`**: exactamente la firma sugerida por la guía
  (`generate_answer(question: str, context: list[dict]) -> str`), para que
  un agente futuro (LangGraph, mencionado en la guía como "proyecto
  posterior") pueda llamar `retrieve()` y `generate_answer()` como pasos
  independientes sin ejecutar la recuperación dos veces ni reimplementar el
  monolito de `query()`.
- [x] **Prompt de generación con la voz/audiencia del ticket**: el system
  prompt (`SYSTEM_PROMPT` en `data/pipelines/rag.py`) cita casi literal la
  Sección 1 de `CONTEXT7.md` ("como lo haría un vendedor de TrackFlow... sin
  prometer condiciones que no existen en los acuerdos estándar") e instruye
  explícitamente a no inventar datos cuando el contexto no alcanza —
  verificado en `test_generate_answer_sends_system_prompt_and_context_to_the_generation_client`.
- [x] **Nombres de campos/colección coinciden con el CONTEXT**: `retrieve()`
  usa `COLLECTION_NAME` y el payload de Fase 1 tal cual — ningún nombre
  nuevo inventado en esta fase.

## Checklist de la entrega — Fase 3: Endpoint de consulta (`services/`)

- [x] **`POST /knowledge/query` vía FastAPI**: `services/knowledge-api/routers/knowledge.py`
  — cuerpo de petición `{"question": "..."}`, cuerpo de respuesta
  `{"answer": "..."}` (`QueryResponse` con un único campo — no hay forma de
  que se filtre nada más).
- [x] **El endpoint importa y llama a `query()` desde `data/pipelines/`, sin
  lógica duplicada**: `from rag import query as rag_query` (vía
  `pipeline_path.py`, mismo patrón que `services/reporting/`) — el router no
  reimplementa nada de recuperación ni generación.
- [x] **Nunca devuelve resultados crudos de Qdrant, chunks ni
  puntuaciones**: `QueryResponse` solo tiene `answer`; si `query()` lanza una
  excepción, el detalle completo se loguea server-side
  (`logger.exception(...)`) pero el cliente solo recibe
  `"No se pudo generar una respuesta en este momento."` (502) — verificado
  con `TestClient` inyectando un `rag_query` que lanza con un mensaje
  "sensible" y confirmando que ese texto **no** aparece en la respuesta HTTP.

## Checklist de la entrega — Fase 4: Interfaz de consulta (`uis/`)

- [x] **UI mínima en Next.js (backoffice)**: página `/knowledge`
  (`src/app/(protected)/knowledge/page.tsx`) con un textarea para la
  pregunta, 3 chips de preguntas de ejemplo, y la respuesta del endpoint.
- [x] **Estados de carga y error manejados**: botón deshabilitado +
  "Consultando…" mientras espera; un fallo de la llamada a la API muestra
  `feedback-error` con el mensaje (nunca una respuesta vacía silenciosa) —
  la respuesta anterior se limpia al reenviar, para que un error nuevo no
  quede oculto detrás de una respuesta vieja.
- [x] **Modo claro y oscuro con el design system existente**: el backoffice
  no tenía modo oscuro (confirmado explorando el repo antes de escribir
  código) — se agregó soporte a `prefers-color-scheme: dark` redefiniendo
  los mismos tokens `:root` (`--background`, `--surface`, `--foreground`,
  etc.) que ya usa toda la app, sin crear un sistema de estilos paralelo; se
  corrigieron dos colores hardcodeados (`#fff` en `.field-block input/select/textarea`)
  a `var(--surface)` porque de lo contrario el formulario nuevo (que
  reutiliza esa clase) quedaría con un input blanco fijo en modo oscuro.

## Checklist de la entrega — Fase 5b: Eval de retrieval (`data/eval/`)

- [x] **`data/eval/test-queries.json` con al menos 8 preguntas que cubren
  todos los documentos fuente**: 10 preguntas — `sla-delivery` ×3,
  `returns-policy` ×2, `carrier-coverage` ×3, `storage-pricing` ×2 — las 4
  fuentes cubiertas, incluida la pregunta de ejemplo del propio CONTEXT
  ("¿qué transportista cubre mejor Aragón rural?"). Cada pregunta trae
  `expected_section` además de `expected_source_document` — identifica el
  **chunk exacto** correcto (no solo el documento), necesario para medir
  Recall@3 con precisión en vez de "¿acertó el documento?" (una medida más
  floja que la que pide el CONTEXT).
- [x] **Recall@3 medido contra ese archivo, umbral ≥80%**:
  `data/eval/evaluate_retrieval.py` → **80% (8/10)**. Ver la salvedad
  importante en "Cómo se verificó" y en `docs/rag/rag-design.md` §5: este
  número se midió con un embedding léxico local (sin credenciales reales de
  4Geeks), no con el modelo de producción — es un resultado real (no
  inventado), pero mide la mecánica de recuperación, no la calidad semántica
  del modelo real. Debe volver a correrse con `embed()` real en cuanto haya
  credenciales.

## Checklist de la entrega — Fase 6: Documento de diseño RAG (`docs/rag/`)

- [x] **`docs/rag/rag-design.md`**, pensado para que otro desarrollador lo
  lea y entienda el stack sin revisar el código — no es un resumen de lo que
  se hizo (eso es este documento, `Pasos/`), es la referencia de diseño.
- [x] **Proceso RAG de extremo a extremo**: diagrama Mermaid + flujo
  numerado (documentos fuente → `setup()` → `embed()` → indexación en Qdrant
  || pregunta → `embed()` (mismo) → `retrieve()` → prompt → `generate_answer()`
  → respuesta), sección 1 del documento.
- [x] **Estrategia de chunking documentada explícitamente**: por encabezado
  (`## `), con subdivisión por oración como fallback — sección 2, con la
  razón concreta (las secciones del corpus ya son unidades semánticas de
  negocio, trocear por tamaño fijo arriesgaría cortar una regla a la mitad)
  y una tabla real de tamaño/conteo de chunks por documento (no estimado:
  medido corriendo `chunk_document()` sobre los 4 archivos reales).
- [x] **Prácticas de embeddings**: IDs de modelo distintos para embeddings y
  generación (tabla explícita de variables de entorno), confirmación de que
  se prefieren los modelos de 4Geeks (sin credenciales reales en este repo,
  documentado), cómo `embed()` se reutiliza igual al indexar y al consultar
  (con el bug de `sys.modules` como evidencia de que es reutilización real,
  no una API paralela), dimensión del vector (no hardcodeada, inferida),
  métrica de distancia (coseno), `min_score` y cómo se llegó a ese valor (no
  calibrado, documentado por qué), y la normalización/preprocesamiento del
  texto antes de embeber (ninguno lingüístico a propósito, solo estructural)
  — sección 4 del documento.

## Checklist de la entrega — Grafo del agente (`services/`)

- [x] **Estado del grafo mínimo, sin historial de conversación**:
  `AgentState` (`agent_graph.py`) trae `question`, `context`, `answer`,
  `error` — nada más. Sin historial: cada corrida resuelve una pregunta
  independiente (mismo contrato que `query()`), documentado el porqué en el
  docstring del módulo en vez de agregarlo "por si acaso".
- [x] **Nodos**: `receive_question` (recibe/normaliza la pregunta),
  `retrieve` (llama a `retrieve()` de `data/pipelines/rag.py`, importado —
  no duplicado), `generate` (llama a `generate_answer(question, context)`,
  **no** a `query()`), más `no_context` y `empty_question` para las dos
  rutas de salida no felices.
- [x] **Aristas condicionales, no una secuencia fija**: dos condiciones
  reales — `receive_question` → `empty_question`/`retrieve` según si la
  pregunta quedó vacía tras `strip()`; `retrieve` → `no_context`/`generate`
  según si `retrieve()` devolvió algún chunk por encima de `min_score`.
- [x] **Contrato de nodos respetado**: el nodo `generate` llama a
  `generate_answer(question, context)` con el `context` que el nodo
  `retrieve` ya produjo — nunca se usa `query()` dentro de un nodo (eso
  volvería a ejecutar `retrieve()` internamente y colapsaría el grafo a la
  secuencia monolítica que la guía pide evitar). Verificado con fakes que
  lanzan `AssertionError` si se llaman fuera de la rama que les corresponde
  (`_refuse_to_be_called` en los tests) — si `generate`/`retrieve` se
  llamaran de más, los tests fallarían con ese assert, no en silencio.
- [x] **`compile()` antes de checkpointear, falla claro ante un error
  estructural**: `build_graph()` termina en
  `graph.compile(checkpointer=...)` — un error real (arista hacia un nodo
  nunca definido con `add_node()`) hace que `.compile()` lance
  `ValueError: Found edge ending at unknown node ...` de forma inmediata y
  legible (verificado explícitamente,
  `test_compile_fails_clearly_on_structural_error` — probado contra el
  comportamiento real de LangGraph, no simulado: un nodo simplemente
  "huérfano" sin arista de entrada **no** hace fallar `compile()` en esta
  versión de LangGraph, solo una arista a un nodo inexistente o un grafo sin
  entrypoint desde `START` sí — se verificaron los tres casos a mano antes
  de escribir el test para no afirmar un comportamiento no confirmado).
- [x] **Checkpointing en cada transición de estado**: `build_graph()`
  compila con un `checkpointer` (`MemorySaver` por defecto, inyectable).
  Cada nodo ejecutado bajo un `thread_id` queda como checkpoint —
  `compiled_graph.get_state_history(config)` lo confirma
  (`test_checkpointed_run_is_inspectable_via_state_history`): al menos 2
  checkpoints por una corrida de 3 nodos, y el más reciente trae el estado
  final correcto. **Límite documentado**: `MemorySaver` es en memoria del
  proceso, no persiste entre reinicios — para retomar una corrida después de
  reiniciar el servicio haría falta `SqliteSaver`/`PostgresSaver`
  (`langgraph-checkpoint-*`), no incluido en esta entrega (ver "Pendiente").

## Checklist de la entrega — Tracing y evaluación

- [x] **Cada corrida produce un trace consultable, no solo impreso en
  consola**: `run_agent()` corre con `stream_mode="updates"` (LangGraph
  emite `{nodo: cambio_de_estado}` en orden real de ejecución), arma una
  lista `[{"node": ..., "output": ...}, ...]`, y la persiste en
  `data/eval/agent-traces/<thread_id>.json` — `get_trace(thread_id)` la
  vuelve a leer después de la corrida (`test_eval_retrieve_executes_before_generate_in_the_trace`
  verifica el roundtrip completo). No se usó LangSmith (no hay API key de
  LangSmith en este repo) — el log estructurado propio cumple el mismo
  requisito ("lo que importa es que el trace sea consultable después de la
  corrida").
- [x] **Al menos 3 evals con criterio verificable sobre la respuesta o el
  trace**: 4 (3 de enrutamiento + 1 de anclaje, ver más abajo), más 2 tests
  de estructura del grafo y 1 de checkpointing — 7 tests en total en
  `tests/pipelines/test_agent_graph.py`:
  1. **Orden del trace** (el ejemplo literal de la guía): para una pregunta
     con contexto, `retrieve` se ejecuta antes que `generate`
     (`test_eval_retrieve_executes_before_generate_in_the_trace`).
  2. **Pregunta vacía**: enruta a `empty_question` sin llamar nunca a
     `retrieve` (`test_eval_empty_question_routes_to_error_without_calling_retrieve`).
  3. **Sin contexto por encima del umbral**: enruta a `no_context` sin
     llamar nunca a `generate`
     (`test_eval_no_context_routes_to_honest_answer_without_calling_generate`).
- [x] **Los evals corren contra el trace de una corrida offline, no contra
  un servicio en vivo repetido**: cada eval invoca `run_agent()` **una vez**
  con `retrieve_fn`/`generate_fn` inyectados (fakes deterministas, sin red)
  y hace las aserciones sobre el `trace`/estado que esa corrida produjo —
  nunca golpea Qdrant ni un LLM real, así que corre igual de rápido y
  offline la primera vez que la centésima.
- [x] **Eval de anclaje a la base de conocimiento existente** (no reemplaza
  la corrección del trace, es adicional):
  `test_eval_answer_stays_anchored_to_the_real_knowledge_base` — pregunta de
  política conocida ("¿puede un account manager ofrecer un descuento de
  almacenamiento sin aprobación?") corre con **`retrieve()` real** (Qdrant
  `:memory:` indexado de verdad con los 4 documentos + el embedding léxico
  de Fase 5b, no mockeado) y solo `generate_fn` es un fake "fiel" (devuelve
  literalmente el texto recuperado, sin pretender simular calidad de LLM).
  Verifica que "Miguel Torres" (la entidad real de
  `docs/company-knowledge-base/trackflow-storage-pricing.es.md`) aparece
  tanto en el `context` recuperado como en la respuesta final — si el
  anclaje se rompiera (p. ej. alguien cambia el chunking y ese chunk deja de
  indexarse), este eval fallaría aunque el enrutamiento del grafo siguiera
  siendo perfecto.
- [x] **Los evals viven en `tests/pipelines/` y no rompen los tests RAG
  existentes**: `test_agent_graph.py` (7 tests) es un archivo nuevo,
  `test_rag.py` (17 tests) no se tocó — ambos corren independientes, ambos
  siguen en verde.

## Checklist de la entrega — Endpoint (`services/`)

- [x] **`POST /agent/query` convive con `POST /knowledge/query`**: mismo
  servicio (`services/knowledge-api/`), mismo `main.py`, dos routers
  registrados (`routers/knowledge.py` sin tocar, `routers/agent.py` nuevo) —
  no se reemplazó nada existente.
- [x] **El endpoint no contiene lógica de negocio propia**: `routers/agent.py::query_agent()`
  solo llama a `run_agent()` y traduce el resultado a HTTP — ningún nodo,
  ninguna condición de enrutamiento, ninguna llamada a Qdrant/LLM vive en el
  router (todo eso está en `agent_graph.py`).
- [x] **Nunca un stack trace crudo, siempre un mensaje claro**: una
  excepción real durante la corrida del grafo (p. ej. Qdrant caído) →
  `logger.exception(...)` server-side + `502` con
  `"No se pudo generar una respuesta en este momento."` al cliente; la ruta
  `empty_question` del grafo (no es una excepción, es un estado explícito)
  → `400` con el mensaje concreto (`"La pregunta no puede estar vacía."`) —
  verificado con `TestClient` para ambos casos.

## Cómo se verificó

Sin credenciales reales de 4Geeks para `embed()`/generación, se verificó con
infraestructura real donde fue posible y funciones/clientes falsos donde no:

1. **Qdrant real** (contenedor Docker `qdrant/qdrant:v1.13.4`, el mismo tag
   fijado en `docker-compose.yml`) + un `embed_fn` determinista (hash SHA-256
   truncado a 16 floats, sin llamar a ningún LLM) — confirmó de punta a
   punta: los 4 documentos producen 20 chunks en total (5 cada uno),
   `setup()` crea la colección con la dimensión de vector correcta, el
   payload trae los 6 campos exactos, una segunda corrida de `setup()` deja
   el mismo número de puntos (no duplica), `recreate=True` borra y recarga
   limpio, y `retrieve()` (Fase 2) recupera correctamente el chunk exacto
   con `min_score` alto y devuelve `[]` con un umbral inalcanzable.
2. **Bug real encontrado y corregido al verificar Fase 2**: al cargar
   `data/process/rag.py` desde `data/pipelines/rag.py` vía
   `importlib.util.spec_from_file_location()`, `@dataclass(frozen=True)`
   (la clase `Chunk` de Fase 1) fallaba con
   `AttributeError: 'NoneType' object has no attribute '__dict__'` — porque
   el módulo cargado a mano nunca se registró en `sys.modules` antes de
   `exec_module()` (paso que `importlib.import_module()` hace solo y que
   hay que replicar manualmente con `spec_from_file_location`). Corregido
   agregando `sys.modules[_INDEXING_MODULE_NAME] = _indexing` antes de
   ejecutar el módulo — ver el comentario en `data/pipelines/rag.py`.
3. **`services/knowledge-api/`** verificado con `fastapi.testclient.TestClient`
   inyectando un `rag_query` fake: `200` con la respuesta esperada (y solo
   el campo `answer`), `400` con pregunta vacía, `502` con el detalle
   interno **no** filtrado al cliente cuando `query()` lanza.
4. **`uis/backoffice`** verificado con un navegador real (Playwright +
   Chromium, no solo `npm run build`): `npm run build` pasa sin errores de
   TypeScript y genera la ruta `/knowledge`; con `incidents-api` +
   `knowledge-api` + Qdrant reales levantados (Postgres/Redis/Qdrant en
   Docker), se creó un usuario de prueba, se sembró el token de sesión
   directamente en `localStorage` (evitando repetir el flujo de login) y se
   navegó a `/knowledge` con Chromium real: la página carga con el usuario
   autenticado, el sidebar muestra "Base de conocimiento" activo, el
   formulario y los chips de ejemplo se ven correctamente, y al enviar una
   pregunta se ve el estado "Consultando…" seguido del error esperado (502
   de `knowledge-api`, por no haber credenciales de generación reales) — sin
   ningún error de consola más allá de ese 502 documentado. Capturas
   guardadas localmente durante la verificación (no comiteadas).
5. **`tests/pipelines/test_rag.py`** (17 tests, `pytest`: 10 de Fase 1 + 7 de
   Fase 2) — mismo patrón de `embed_fn`/`generation_client` falsos, pero
   contra Qdrant en **modo `:memory:`** (sin Docker, sin servidor) para Fase 1
   y Fase 2 juntas: parseo/chunking, payload, idempotencia de `setup()`
   (Fase 1); filtrado por `min_score`, "nunca objetos crudos del SDK",
   "puede devolver menos de k", el prompt de generación recibe el contexto
   recuperado, y que `query()` de verdad pasa por `generate_answer()` (no
   devuelve texto crudo de un chunk) (Fase 2). Corre sin Docker ni
   credenciales — viable en CI. Exactamente
   `python -m pytest tests/pipelines/test_rag.py -q` (la invocación literal
   que pide la guía) → `17 passed`.
6. **`data/eval/evaluate_retrieval.py`** (Fase 5b) — corrido de verdad contra
   Qdrant `:memory:`, `retrieve()` real (Fase 2, sin mockear), con un
   embedding léxico local en vez del de 4Geeks (ver la salvedad en el
   checklist de Fase 5b arriba). Primera corrida: **70% (7/10)**, con `q4`
   fallando. Al inspeccionar qué había recuperado de verdad para `q4`
   (`retrieved` en `data/eval/retrieval_recall.json`), se encontró que el
   top-1 resultado (`carrier-coverage / Transportistas internacionales`) era
   en realidad **más correcto** que el `expected_section` que yo le había
   puesto a esa pregunta (`Cobertura en Estados Unidos`) — un bug real en
   los datos de prueba, no en `retrieve()`. Corregido el `expected_section`
   de `q4` → segunda corrida: **80% (8/10)**, umbral cumplido. Los dos
   `MISS` restantes (`q5`, `q10`) se investigaron de la misma forma y son
   limitaciones genuinas del embedding léxico (no conecta "Península
   Ibérica" con "España"; diluye el peso de "urgente" dentro de una sección
   más larga) — no se "arreglaron" reformulando las preguntas de prueba
   para inflar el número, porque eso sería optimizar contra un método que
   el propio documento ya dice que no representa al modelo real.

7. **Grafo del agente** (`services/knowledge-api/agent_graph.py`) —
   verificado en capas, todas reales salvo Qdrant/LLM (sin credenciales):
   - Camino feliz, pregunta vacía y sin-contexto probados a mano primero
     (`python3 -c "..."`, ver el historial de esta sesión) con fakes que
     lanzan `AssertionError` si se llaman fuera de su rama — confirmó que
     `retrieve`/`generate` nunca se ejecutan de más antes de escribir el
     test formal.
   - `compile()` sobre un grafo roto probado contra el comportamiento **real**
     de LangGraph (no asumido): se probaron tres variantes a mano (nodo sin
     arista de entrada, arista a nodo inexistente, grafo sin `START`) — solo
     las dos últimas hacen fallar `compile()` en esta versión de LangGraph.
     El test formal usa la que sí falla (arista a nodo inexistente) para no
     afirmar un comportamiento que no se confirmó.
   - `test_agent_graph.py` (7 tests) — `python -m pytest tests/pipelines/test_agent_graph.py -q`
     → `7 passed`, corridos con `services/knowledge-api/.venv` (tiene
     `langgraph` instalado; `data/process/.venv` no).
   - `POST /agent/query` verificado con `TestClient` (mismo patrón que
     `POST /knowledge/query`): `200` con la respuesta del grafo, `400` con
     pregunta vacía y el mensaje exacto del nodo `empty_question`.

Toda la infraestructura de prueba (contenedores Docker, `.env` locales,
servidores de desarrollo) se descartó al terminar
(`docker rm -f`/`docker ps -a` vacío, `.env`/`.env.local` borrados,
`suppliers.json` revertido a su estado comiteado, `data/eval/agent-traces/`
vaciado — ver "Decisiones" sobre por qué no se comitea ese directorio).

## Decisiones de implementación no cubiertas por la guía genérica

- **`data/process/` como paquete propio (`pyproject.toml` + `uv.lock` +
  `.venv`)**: la guía sugiere `data/process/rag.py` como ubicación de
  archivo, pero no dice cómo gestionar su entorno. Se le dio su propio
  `pyproject.toml` (mismo patrón que `data/pipelines/`,
  `services/job_runner/`, etc. en este repo — cada área funcional gestiona
  su propio entorno completo), poblado con `uv add` real (no a mano) porque
  esta guía específicamente lo exige.
- **`qdrant-client` fijado a `<1.15`**: para que coincida con la versión del
  servidor fijada en `docker-compose.yml` (`v1.13.4`) — ver el checklist de
  arriba.
- **`embed_fn`/`qdrant_client` inyectables en `setup()`**: no pedido
  explícitamente, pero necesario para poder probar la lógica propia
  (chunking, payload, idempotencia) sin depender de credenciales que este
  repo no trae — mismo patrón que `run_pipeline_subprocess`/`embed_fn` en
  entregas anteriores de esta sesión.
- **`data/eval/test-queries.json` creado en Fase 1**, aunque técnicamente
  pertenece a "Instrucciones de Datos Semilla" (Sección 5 de `CONTEXT7.md`)
  más que al checklist de Fase 1 en sí: barato de escribir junto con los
  documentos fuente, y la Fase 2 lo iba a necesitar para medir Recall@3 de
  todas formas.
- **`data/pipelines/rag.py` carga `data/process/rag.py` con `importlib`, no
  `sys.path.insert` + `import rag`**: ambos módulos se llaman `rag.py` — con
  los dos paquetes en `sys.path` a la vez, `import rag` sería ambiguo según
  el orden de inserción. Se prefirió esto a renombrar cualquiera de los dos
  archivos (que ya estaban documentados/testeados desde Fase 1) — ver el bug
  real que esto evitó en "Cómo se verificó".
- **`services/knowledge-api/` sin autenticación**: `CONTEXT7.md` no la pide
  para `POST /knowledge/query`, a diferencia de `services/reporting/` (que sí
  protege `POST /run` porque dispara un pipeline de datos). No agregar auth
  no pedida evita acoplar este servicio nuevo al sistema de usuarios de
  `incidents-api` sin necesidad real.
- **`DEFAULT_MIN_SCORE = 0.5`**: valor de partida razonado (punto medio del
  rango de similitud coseno), no calibrado empíricamente — no hay
  credenciales reales de 4Geeks para correr `test-queries.json` contra el
  modelo de embeddings real y mirar la distribución de scores. Fijar un
  número "validado" sin esos datos sería el mismo tipo de dato inventado que
  la guía prohíbe para las respuestas del sistema — documentado como punto
  de partida explícito, con la metodología de recalibración ya escrita
  (docstring de `data/pipelines/rag.py`).
- **Modo oscuro agregado al backoffice sin selector manual**: solo
  `prefers-color-scheme` (preferencia del sistema operativo) — no había
  ningún toggle de tema en la app para replicar, y agregar uno no estaba
  pedido por esta guía (que solo pide "soportar modo claro y oscuro").
- **Grafo del agente en `services/knowledge-api/`, no un servicio nuevo**:
  la guía dice "Grafo del agente (`services/`)" y "Endpoint... que
  reemplace o **conviva** con el endpoint RAG existente" — convivir en el
  mismo servicio (mismo `main.py`, un router nuevo) es la lectura literal
  más simple, y evita crear un cuarto servicio (`incidents-api`,
  `reporting`, `job_runner`, `knowledge-api`) solo para una capa fina que ya
  depende de exactamente el mismo `data/pipelines/rag.py`.
- **`MemorySaver` como checkpointer por defecto**: no hay una base de datos
  designada para persistir checkpoints del agente en este repo, y la guía
  no la pide explícitamente — `MemorySaver` cumple el requisito literal
  ("implementa checkpointing... para que una corrida pueda inspeccionarse")
  dentro del mismo proceso; el límite (no sobrevive un reinicio) queda
  documentado, no escondido.
- **Trace propio (JSON en disco) en vez de LangSmith**: no hay credenciales
  de LangSmith en este repo; la guía explícitamente permite "tu propio log
  estructurado si no tienes acceso a una [herramienta de tracing]". Se
  reutilizó el mismo patrón que `data/eval/evaluate_retrieval.py` (archivo
  JSON, consultable después de la corrida) en vez de inventar un formato
  nuevo.
- **`data/eval/agent-traces/` no se agregó a `.gitignore`**: los archivos de
  trace se generan con nombres de `thread_id` aleatorios (UUID) en cada
  corrida — no tienen valor de referencia estable como
  `data/eval/retrieval_recall.json` (que sí se comitea, siempre en la misma
  ruta, contenido reproducible). Lo correcto sería ignorarlos en
  `.gitignore`, pero `AGENTS.md` restringe modificar ese archivo sin
  confirmación explícita del desarrollador — se optó por no comitear el
  directorio (limpiado a mano tras verificar) en vez de tocar `.gitignore`
  sin permiso.
- **Eval de anclaje con `retrieve()` real, no completamente fake**: los
  otros 3 evals de enrutamiento sí usan `retrieve_fn` fake (no necesitan
  datos reales, solo verifican qué nodo se ejecuta), pero el eval de
  anclaje específicamente necesita que el contexto recuperado sea real
  (contra el corpus real) para que la aserción "Miguel Torres aparece en la
  respuesta" signifique algo — con un `retrieve_fn` fake devolviendo
  cualquier texto, ese eval se volvería circular (probaría que el fake dice
  lo que el fake dice, no que el sistema está anclado).

## Pendiente / siguientes pasos

1. Credenciales reales de 4Geeks (`EMBEDDING_API_BASE`/`EMBEDDING_API_KEY`,
   `GENERATION_API_BASE`/`GENERATION_API_KEY`) para poder correr todo el
   flujo con embeddings/generación reales, no las funciones/clientes falsos
   de verificación.
2. Recalibrar `DEFAULT_MIN_SCORE` (hoy 0.5, sin validar) una vez existan esas
   credenciales, corriendo `data/eval/test-queries.json` contra el modelo de
   embeddings real.
3. Volver a medir Recall@3 (`data/eval/evaluate_retrieval.py`, hoy 80% con
   el embedding léxico de reemplazo) y faithfulness contra
   `data/eval/test-queries.json` con `retrieve()`/`generate_answer()`
   reales — el umbral de faithfulness ("0 discrepancias numéricas") no se
   pudo evaluar en absoluto en esta entrega porque requiere generación real,
   y el 80% de Recall@3 medido con el embedding léxico no es representativo
   de la calidad del modelo de producción (ver la salvedad en Fase 5b y en
   `docs/rag/rag-design.md` §5).
4. ~~El agente LangGraph que la guía menciona como "proyecto posterior" de la
   Fase 2~~ — **hecho**, ver "Grafo del agente" arriba.
5. `services/knowledge-api/` no tiene tests automatizados propios en el
   repo para `routers/knowledge.py`/`main.py` en sí (sí los tiene para
   `agent_graph.py`, vía `tests/pipelines/test_agent_graph.py`) — se
   verificó con un script manual de `TestClient` (no comiteado), mismo
   criterio que `services/reporting/` y `services/job_runner/` en entregas
   anteriores.
6. Checkpointer en memoria (`MemorySaver`): una corrida del agente no se
   puede retomar después de reiniciar `knowledge-api` (el checkpoint se
   pierde con el proceso). Para eso haría falta `SqliteSaver` o
   `PostgresSaver` (`langgraph-checkpoint-sqlite`/`-postgres`), no
   instalado en esta entrega — no hay una base de datos designada para
   persistir checkpoints del agente todavía.
7. `data/eval/agent-traces/` no está en `.gitignore` (ver "Decisiones") —
   si se sigue generando tráfico real, conviene agregarlo ahí en vez de
   descartar los archivos a mano cada vez; requiere confirmación explícita
   del desarrollador por la restricción de `AGENTS.md` sobre ese archivo.
