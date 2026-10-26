# Generación por departamento y evaluación en paralelo — Hito 9 · Parte 2

Fecha: 2026-10-26

Implementación de `CONTEXT/CONTEXT9.md` (Hito 9, Parte 2): consume el
handoff que dejó la Parte 1 (ticket en `analisis_completo`, con
`RFPDepartmentSection.key_aspects` ya persistido por departamento) para
generar el borrador de la sección de propuesta económica de cada
departamento activo, y evaluarlo en paralelo con 3 agentes evaluadores
independientes (legibilidad, pertinencia, cumplimiento), persistiendo el
resultado como un `EvaluationResult` estructurado.

El checklist se compartió en dos imágenes: la primera (recibida primero)
se veía cortada justo después de `overall_pass: bool`; la segunda
completó exactamente lo que faltaba -- el campo `feedback_for_generator`
en `EvaluationResult`, el ciclo generador-evaluador con límite de
iteraciones, y la transición de estado del ticket a
`generando_borrador`/`en_evaluación`/`needs_human_review`. Ambas rondas
quedan documentadas juntas en este archivo (mismo Hito, misma Parte).

## Dónde vive el código

```
data/pipelines/rfp_intake/
  generators.py            # NUEVO -- un generador determinista por departamento, reacciona a `feedback`
  evaluators.py             # NUEVO -- ReadabilityEvaluation/RelevanceEvaluation/ComplianceEvaluation/EvaluationResult
  generation_graph.py        # NUEVO -- fan-out dinámico a los generadores de los departamentos activos
  evaluation_graph.py        # NUEVO -- fan-out estático a los 3 evaluadores, converge en un nodo `combine`
  pipeline.py                # EXTENDIDO -- process_rfp_generation(ticket_id) + ciclo generador-evaluador

services/incidents-api/
  rfp_tasks.py                # EXTENDIDO -- process_rfp_generation_task (Celery)
  routers/rfp.py               # EXTENDIDO -- POST /rfp/tickets/{id}/generate

tests/pipelines/
  test_rfp_generators_evaluators.py            # NUEVO
  test_rfp_generation_evaluation_graphs.py       # NUEVO
  test_rfp_generation_cycle.py                   # NUEVO -- ciclo generador-evaluador, límite de iteraciones
```

## Cómo correrlo

```bash
# Backend (API + Celery + Postgres + Redis ya deben estar arriba, igual que Parte 1)
cd services/incidents-api
uvicorn main:app --reload

# En otra terminal
celery -A celery_app worker --loglevel=info

# Disparar generación + evaluación para un ticket que ya está en analisis_completo
curl -X POST http://localhost:8000/rfp/tickets/<id>/generate -H "Authorization: Bearer <token>"

# Consultar resultado (draft_content + evaluation_results por sección)
curl http://localhost:8000/rfp/tickets/<id> -H "Authorization: Bearer <token>"
```

```bash
# Tests (sin Postgres/Celery, deterministas)
cd data/pipelines
.venv/bin/python -m pytest ../../tests/pipelines/test_rfp_generators_evaluators.py \
  ../../tests/pipelines/test_rfp_generation_evaluation_graphs.py \
  ../../tests/pipelines/test_rfp_generation_cycle.py -v
```

## Checklist de la entrega

### Consumir el enrutamiento de la Parte 1

- [x] **`process_rfp_generation(ticket_id)` lee el handoff ya persistido**
  (`RFPMetadataRecord.client_country`/`departments_needed` +
  `RFPDepartmentSection.key_aspects` por departamento) -- nunca vuelve a
  convertir el PDF ni a correr el grafo de Parte 1.
- [x] **Guarda de estado explícita**: si el ticket no está en
  `analisis_completo`, `process_rfp_generation` lanza `ValueError` (y el
  router responde `409`) en vez de generar sobre un ticket a medio
  procesar o ya avanzado -- probado en vivo (ver "Cómo se verificó").
- [x] **Transición de estado del ticket**: `analisis_completo` →
  `generando_borrador` (antes de correr los grafos) → `en_evaluación` (si
  todas las secciones terminaron pasando) **o** `needs_human_review` (si
  al menos una sección agotó el límite de iteraciones sin pasar) -- los 3
  estados siguientes de la tabla de `CONTEXT9.md` §2.3, nunca
  `descartado` (ver "Ciclo generador-evaluador").

### Generación por departamento

- [x] **Un generador por departamento** (`generators.py`): cada función
  `(key_aspects, client_country) -> str` -- recibe únicamente el handoff
  de la Parte 1, **nunca** el Markdown/PDF original.
- [x] **Nunca inventa una cifra**: cuando un `key_aspect` no vino de la
  Parte 1 (p. ej. `monthly_volume` ausente), la plantilla dice
  explícitamente "a confirmar con el cliente" en vez de inventar un
  número.
- [x] **Compliance-by-design**: cada plantilla ya respeta por
  construcción moneda correcta, tabla de descuentos, SLA declarado
  (lastmile), ≥48h de procesamiento de devoluciones (reverse, 72h con
  margen), y nunca revela una tarifa negociada con un carrier --
  `evaluators.py` lo vuelve a chequear de forma independiente, sin
  confiar ciegamente en que la plantilla nunca falle.
- [x] **Fan-out dinámico a solo los departamentos activos**
  (`generation_graph.py`): mismo patrón ya verificado en la Parte 1
  (arista condicional que devuelve una lista de nodos, cada uno con su
  propia clave de estado `{dept}_draft`).

### Evaluación en paralelo

- [x] **3 evaluadores independientes que corren en paralelo de verdad**
  (`evaluation_graph.py`): `START` tiene una arista hacia cada uno de los
  3 nodos (`readability`/`relevance`/`compliance`), cada uno escribe a su
  propia clave de estado, y un nodo `combine` converge una sola vez que
  los 3 terminaron -- no es una llamada secuencial a 3 funciones.
- [x] **Legibilidad con `py-readability-metrics`**:
  `evaluate_readability()` reutiliza
  `pdf_conversion.compute_readability_metrics()` (Parte 1) sobre el
  borrador generado.
- [x] **Pertinencia**: `evaluate_relevance()` verifica que cada
  `key_aspect` real (no inventado, viene de la Parte 1) aparezca
  mencionado en el borrador -- si algo que el cliente pidió no se
  menciona, se reporta en `missing_aspects`.
- [x] **Cumplimiento según `CONTEXT9.md` §5**: `evaluate_compliance()`
  implementa los 5 lineamientos literales de la Sección 5 ("Restricciones
  de negocio") -- moneda correcta según `client_country`, SLA de entrega
  declarado (solo lastmile), nunca <48h de procesamiento de devoluciones
  (solo reverse), tabla de descuentos por volumen presente (todos), nunca
  revelar una tarifa negociada con un carrier específico (todos).
- [x] **`EvaluationResult` estructurado y persistido**: el schema exacto
  del checklist (`pass`/`score`/`details` para legibilidad;
  `pass`/`missing_aspects[]` para pertinencia;
  `pass`/`rule_ids[]`/`violations[]` para cumplimiento; `overall_pass:
  bool` combinado; `feedback_for_generator: string`) -- con `pass` como
  alias Pydantic de `passed` (`pass` es palabra reservada en Python),
  serializado con `model_dump(by_alias=True)` para que la clave
  persistida sea literalmente `"pass"`.
- [x] **`overall_pass` solo es `true` si las 3 evaluaciones pasan**.

### Ciclo generador-evaluador

- [x] **`feedback_for_generator` concreto y accionable**:
  `evaluators.py::build_feedback_for_generator()` compone una frase por
  cada evaluación que falló, citando los `missing_aspects` reales y los
  `violations` reales (con su `rule_id` literal) -- nunca un genérico
  "corrige los errores".
- [x] **Si una sección falla, el flujo vuelve al generador de ESE
  departamento junto con el `feedback_for_generator`**:
  `pipeline.py::_generate_and_evaluate_with_retries()` reinvoca
  `GENERATOR_REGISTRY[department_id](key_aspects, client_country,
  feedback=...)` -- cada generador reacciona de forma determinista a los
  mismos tokens (`missing_aspects`, `rule_id`) que el feedback siempre
  contiene (`generators.py::_apply_feedback`), agregando una aclaración
  puntual por cada falla real -- no es una regeneración idéntica
  disfrazada de reintento (ver "Cómo se verificó").
- [x] **Límite de iteraciones** (`MAX_GENERATION_ITERATIONS = 3`) para
  que el ciclo nunca se repita indefinidamente.
- [x] **Al agotar el límite sin pasar: conserva el último borrador + su
  `EvaluationResult` real, marca la sección como `needs_human_review`, y
  nunca descarta el ticket**: `section.approval_status =
  "needs_human_review"` (campo ya predeclarado desde la Parte 1 para
  exactamente este uso) -- `get_ticket_with_metadata()` sigue devolviendo
  la sección normalmente, incluida en el handoff a la Parte 3.

### Estado del ticket

- [x] **Actualiza el ticket creado en la Parte 1** reflejando el progreso
  real (`generando_borrador` → `en_evaluación`/`needs_human_review`).
- [x] **Persiste borradores y `evaluation_results` en PostgreSQL**, sin
  crear un API nuevo -- extiende `services/incidents-api` existente y el
  pipeline bajo `data/pipelines/`.
- [x] **Los lineamientos de negocio contra los que se evalúa coinciden
  con `CONTEXT9.md` §5** (el "company-BRIEFING.md" de este curso) --
  moneda por `client_country`, SLA solo lastmile, ≥48h solo reverse,
  tabla de descuentos siempre, nunca revelar tarifa negociada -- nunca
  una lista de reglas genérica que ignore el contexto real de TrackFlow.

## Cómo se verificó

Sin credenciales de 4Geeks para generación/evaluación por LLM (mismo
límite documentado en toda esta sesión), pero con LangGraph real,
py-readability-metrics real, Postgres real, Celery real, HTTP real, y los
tickets reales ya persistidos por la Parte 1 (nunca datos de prueba
inventados para esta verificación):

1. **Problema real encontrado y corregido antes de seguir -- plantillas
   demasiado cortas para medir legibilidad**: las primeras versiones de
   `generators.py` (58/87/61 palabras) caían bajo el mínimo de 100
   palabras de `py-readability-metrics`, lo que habría hecho que el
   evaluador de legibilidad reportara `"insufficient_text"` casi siempre
   en vez de un score real. Corregido agregando prosa explicativa
   genuina a cada plantilla (112/125/100 palabras finales), confirmado
   con scores reales (Flesch Reading Ease 22-32, rango
   "difficult"/"very_confusing" -- mismo sesgo de calibración al inglés
   ya documentado en `Pasos/rag-knowledge-base-fase1.md`).
2. **Bug real encontrado y corregido -- pertinencia con falso positivo en
   `client_country`**: `workers.py` (Parte 1) guarda
   `key_aspects["client_country"]` para warehouse, pero
   `generate_warehouse_section` solo lo convertía a una moneda (`"USD"`),
   nunca lo mencionaba como texto -- el chequeo genérico de pertinencia
   (sustring de cada valor de `key_aspects` en el borrador) lo marcaba
   siempre como `missing_aspects`. Encontrado corriendo
   `evaluate_relevance` contra `key_aspects` con la forma real que
   produce `run_warehouse_worker`, no datos de prueba simplificados --
   corregido agregando una línea real ("Ubicación de la operación: ...")
   a la plantilla, no ocultando el campo del chequeo.
3. **Bug real encontrado y corregido -- falso positivo con flags
   booleanos**: `key_aspects["special_handling"] = True` (lastmile)
   nunca puede aparecer como el texto literal `"True"` en un borrador
   bien escrito -- el chequeo de pertinencia lo marcaba como
   `missing_aspects` sin importar qué tan bien lo mencionara la
   plantilla. Corregido excluyendo valores `bool` del chequeo de
   sustring genérico (no hay una forma genérica de verificar que un flag
   booleano se haya "mencionado" sin inventar una lista de frases
   esperadas por campo).
4. **Evaluador de cumplimiento probado contra un borrador deliberadamente
   no conforme** (no solo contra el camino feliz): un texto con moneda
   incorrecta, sin tabla de descuentos, devoluciones en 24h, y una
   tarifa negociada con UPS revelada -- `evaluate_compliance` atrapó las
   4 violaciones reales, confirmando que el evaluador reprueba cuando
   debe, no solo que nunca falle.
5. **`tests/pipelines/test_rfp_generators_evaluators.py` (17 tests) +
   `test_rfp_generation_evaluation_graphs.py` (4 tests) +
   `test_rfp_generation_cycle.py` (4 tests), 25/25 en verde**, corridos
   junto con los 19 tests de Parte 1 (`test_rfp_classifier.py` +
   `test_rfp_workers.py`) -- 42/42 sin regresiones.
6. **Ciclo generador-evaluador probado con fallos forzados reales, no
   solo el camino feliz**: `test_rfp_generation_cycle.py` inyecta
   `generator_fn`/`evaluate_fn` falsos para probar, de forma
   determinista, los 3 caminos reales del ciclo -- (a) pasa al primer
   intento y NUNCA vuelve a llamar al generador (`_refuse_to_be_called`
   confirma que no hay un reintento innecesario); (b) falla una vez,
   recibe el `feedback_for_generator` real de esa evaluación (se
   confirma que no es `None` ni genérico, contiene el `rule_id` real) y
   pasa en el segundo intento; (c) falla siempre, agota las 3
   iteraciones, y confirma `needs_human_review=True` con el último
   borrador + evaluación preservados (nunca `None`). Un cuarto test
   confirma que el generador REAL de `reverse` (compliant-by-design)
   pasa al primer intento sin necesitar nunca un reintento.
7. **Reintento con feedback probado contra el generador REAL, no solo con
   fakes**: se fabricó un borrador deliberadamente no conforme (24h de
   devoluciones, tarifa negociada con UPS revelada), se evaluó con
   `evaluate_compliance` real (confirmó 2 violaciones reales), y se le
   pasó el `feedback_for_generator` resultante a
   `generate_reverse_section(..., feedback=...)` real --
   `_apply_feedback` reconoció los tokens `no_negotiated_carrier_rates` y
   `returns_48h_minimum` en el feedback y agregó las aclaraciones
   correctas; el borrador regenerado vuelve a pasar `evaluate_compliance`
   limpio.
8. **Flujo completo verificado de punta a punta con infraestructura
   real**: Postgres real (mismo contenedor `trackflow-pg-mcp` de
   sesiones anteriores), llamando directamente
   `process_rfp_generation()` contra los tickets 1, 2 y 5 (ya
   persistidos por la Parte 1 -- ModaViva: warehouse+reverse; Luna
   Cosmetics: warehouse+lastmile) -- confirmado que `draft_content` y
   `evaluation_results` (incluido `feedback_for_generator`) quedan
   realmente escritos en `RFPDepartmentSection` (no solo devueltos en
   memoria), con `overall_pass=true` en las 6 secciones generadas.
9. **Escalamiento a `needs_human_review` probado contra Postgres real,
   no solo en memoria**: con `_generate_and_evaluate_with_retries`
   forzado a devolver `needs_human_review=True` (mismo patrón de
   inyección que el resto de esta sesión), se corrió
   `process_rfp_generation(8)` real -- confirmado en la base: 
   `RFPTicket.status="needs_human_review"` y
   `RFPDepartmentSection.approval_status="needs_human_review"` en ambas
   secciones, con `draft_content`/`evaluation_results` reales
   preservados (nunca `NULL`, nunca descartados). También se confirmó
   que `get_ticket_with_metadata(8)` sigue devolviendo el ticket y sus
   secciones con normalidad -- el handoff a la Parte 3 no pierde
   tickets escalados.
10. **Flujo HTTP + Celery real, extremo a extremo**: `uvicorn` real +
    worker de Celery real + un usuario registrado y autenticado de
    verdad (`POST /users` + `POST /auth/login`) + `POST
    /rfp/tickets/4/generate` (el ticket 4, otra copia de ModaViva de la
    Parte 1, aún sin tocar) con bearer token real -- `202` inmediato,
    Celery procesó la tarea, y `GET /rfp/tickets/4` confirmó
    `status="en_evaluación"` con ambas secciones (`warehouse`,
    `reverse`) con `draft_content` y `evaluation_results` reales, moneda
    `EUR` correcta para `client_country="Spain"`.
11. **Guarda de estado probada por HTTP real, no solo unitariamente**:
    repetir `POST /rfp/tickets/4/generate` sobre el mismo ticket (ya en
    `en_evaluación`) devolvió `409` real con el mensaje explicando el
    estado esperado vs. el actual.
12. **Limpieza tras la verificación**: `.env` temporal de
    `services/incidents-api` eliminado, usuario de prueba revertido de
    `suppliers.json` (`git checkout --`), procesos de `uvicorn`/`celery`
    terminados -- los tickets 1, 2, 4 y 5 quedan avanzados a
    `en_evaluación` y el ticket 8 queda en `needs_human_review` en
    Postgres, como evidencia real de la verificación (misma lógica que
    la Parte 1: esos tickets ya eran fixtures de smoke-test, no datos de
    producción; el ticket 7 también quedó avanzado de una verificación
    previa de esta misma ronda).
13. **La UI del backoffice (`rfp-intake-panel.tsx`) no se extendió esta
    ronda** -- el checklist compartido no pedía explícitamente un cambio
    de UI para la Parte 2 (a diferencia de la Parte 1, que sí lo pedía), y
    no había tiempo de verificarlo en un navegador real dentro de esta
    entrega. El endpoint ya es invocable por HTTP real (punto 10) con el
    mismo contrato que usaría un futuro botón "Generar propuesta".

## Decisiones de implementación no cubiertas por la guía genérica

- **`generation_graph.py` sin nodo `orchestrate`/`synthesize`**: a
  diferencia del grafo de Parte 1, acá no hace falta un paso explícito de
  orquestación (la decisión de qué departamentos están activos ya la
  tomó la Parte 1) ni de síntesis (cada borrador se persiste por separado,
  no se combina en un resumen único) -- agregar esos nodos habría sido
  estructura especulativa copiada de Parte 1 sin una razón real en Parte
  2.
- **`evaluation_graph.py` con fan-out ESTÁTICO, no condicional**: a
  diferencia de `generation_graph.py` (que sí necesita decidir
  dinámicamente qué departamentos corren), los 3 evaluadores siempre
  corren sobre cualquier sección generada -- no hay una condición de
  negocio que determine si "legibilidad" o "cumplimiento" aplican o no,
  así que 3 aristas simples desde `START` son más honestas que una arista
  condicional que siempre devolvería la misma lista.
- **Umbral de legibilidad bajo (`MIN_FLESCH_READING_EASE = 10.0`), no el
  30+ "estándar" de la literatura de Flesch**: la fórmula está calibrada
  para inglés: texto de negocio en español razonable puntúa
  sistemáticamente "very_confusing"/"difficult" (ya visto con el mismo
  patrón en `Pasos/rag-knowledge-base-fase1.md`). Un umbral alto
  reprobaría por legibilidad casi cualquier texto en español sin importar
  qué tan claro esté escrito -- el umbral bajo deja que el evaluador siga
  siendo útil (sí reprueba texto genuinamente demasiado corto o ilegible)
  sin heredar el sesgo de idioma de la librería como si fuera una regla
  de negocio real.
- **Pertinencia excluye valores booleanos del chequeo de sustring**: ver
  bug #3 de "Cómo se verificó" -- un flag como `special_handling: True`
  no tiene una representación textual única que buscar; incluirlo
  producía falsos positivos sistemáticos, así que se excluye en vez de
  mantener un chequeo que miente sobre lo que realmente verifica.
- **`process_rfp_generation` valida el estado del ticket con una excepción
  explícita (`ValueError`), no silenciosamente**: reprocesar un ticket
  que no está en `analisis_completo` (ya avanzado, o todavía en
  `analizando`) es un error de uso real, no un caso a tolerar -- mismo
  principio de "no fallar en silencio" que ya rige el resto del pipeline
  desde la Parte 1.
- **Nueva tarea Celery (`process_rfp_generation_task`) en vez de
  reutilizar `process_rfp_ticket_task`**: son dos operaciones de negocio
  distintas sobre el mismo ticket (clasificar+rutear vs.
  generar+evaluar) -- mismo principio que llevó a `graph.py` vs.
  `generation_graph.py`/`evaluation_graph.py` como grafos separados en
  vez de uno solo con ramas gigantes.
- **El ciclo generador-evaluador vive en Python (`pipeline.py`), no como
  un tercer grafo LangGraph con un ciclo real**: `generation_graph.py`
  sigue usándose tal cual para el intento inicial (fan-out paralelo real
  de todos los departamentos activos) y `evaluation_graph.py` para cada
  evaluación (fan-out paralelo real de los 3 evaluadores); los
  REINTENTOS llaman directamente a `GENERATOR_REGISTRY[department_id]` +
  `evaluation_graph` dentro de un `for` acotado por
  `MAX_GENERATION_ITERATIONS`. Modelarlo como un tercer grafo con una
  arista condicional de vuelta a `generate` habría sido técnicamente
  posible, pero habría duplicado lógica que los dos grafos existentes ya
  resuelven bien (fan-out inicial paralelo, evaluación paralela por
  sección) solo para expresar un control de flujo (contar intentos,
  decidir cuándo escalar) que es más simple y más legible como Python
  liso -- mismo criterio que ya justificó no fusionar generación y
  evaluación en un solo grafo.
- **`MAX_GENERATION_ITERATIONS = 3`**: `CONTEXT9.md` solo da una pista
  indirecta ("Iteraciones promedio por sección... ideal: menos de 2"),
  no un número exacto -- 3 (intento inicial + 2 reintentos con feedback)
  deja margen holgado sobre ese ideal sin permitir un ciclo indefinido;
  nunca verificado contra un valor "oficial" porque el checklist no dio
  uno.
- **`feedback_for_generator` se interpreta por reconocimiento de tokens
  literales (`missing_aspects`, `rule_id`), no por un LLM que "entienda"
  el texto**: mismo límite de siempre (sin credenciales de 4Geeks) --
  `_apply_feedback` (`generators.py`) busca substrings exactos de los
  mismos tokens que `evaluators.py` siempre escribe, y agrega una
  aclaración puntual por cada uno. Es un mecanismo real y determinista
  (probado regenerando un borrador deliberadamente no conforme, ver
  "Cómo se verificó" #7), aunque más limitado que lo que haría un LLM
  real con el mismo feedback.
- **`needs_human_review` se marca reutilizando
  `RFPDepartmentSection.approval_status`, sin una columna nueva**: ese
  campo ya existía desde la Parte 1 explícitamente predeclarado para
  "que Partes 2 y 3 no necesiten una migración nueva" -- se le asigna el
  string `"needs_human_review"` cuando se agota el límite de iteraciones
  (y queda `None` en cualquier otro caso, incluido "aprobado, pendiente
  del flujo de aprobación de la Parte 3"). `esperando_aprobación`
  (`TicketStatus`) sigue sin usarse -- pertenece al flujo de aprobación
  humana explícito que previsiblemente trae la Parte 3, no a esta
  entrega.

## Pendiente

- **UI del backoffice**: no se agregó un botón/vista para disparar
  `POST /rfp/tickets/{id}/generate` ni para mostrar `draft_content`/
  `evaluation_results` en `rfp-intake-panel.tsx` -- el checklist
  compartido no lo pedía explícitamente para esta Parte (a diferencia de
  la Parte 1), y el endpoint ya es invocable por HTTP real con el mismo
  contrato que usaría esa UI futura.
- **Sección "Pruebas" del checklist**: la segunda imagen compartida
  mostraba el título "Pruebas" al final, sin bullets visibles (cortada
  igual que la sección "Ciclo generador-evaluador" lo estuvo en la
  primera imagen) -- no se adivinó su contenido. Esta entrega sí incluye
  tests reales y verificación en vivo (ver "Cómo se verificó"), pero sin
  ver el bullet exacto no se sabe si el checklist pedía algo adicional
  específico (p. ej. un tipo de prueba o cobertura particular) que no
  esté ya cubierto.
