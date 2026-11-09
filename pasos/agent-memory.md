# Memoria y auto-mejora del agente (Hito 8 · Parte 1)

Fecha: 2026-10-05 — actualizado 2026-10-05 (Consolidación y Limpieza +
Evidencia)

Implementación de `CONTEXT/CONTEXT8.md` ("Memoria y Auto-mejora de
Agentes"): un backend de memoria persistente para el agente de
`services/knowledge-api` (el mismo que `CONTEXT7.md`/Hito 7 construyó),
auto-evaluación y propuesta de memoria en la misma respuesta, confirmación
del usuario con registro auditable, un mecanismo real de consolidación con
política de expiración/capacidad, y evidencia documentada de los dos ciclos
completos del flujo (aprobado y rechazado). **No incluye** la sección
"Decisiones de Diseño" del checklist: la segunda captura de pantalla
compartida cortaba justo en ese encabezado ("Como parte del reto, tu
implementación debe resolver — sin que se te diga explícitamente en un
checklist — las siguientes decisiones:"), sin ningún bullet visible debajo
— pendiente de que se comparta el resto (ver "Pendiente").

Antes de implementar, leí `CONTEXT/CONTEXT8.md` completo (las restricciones
específicas de TrackFlow: qué sí/nunca es memorizable, los ejemplos de la
sección "Auto-evaluación", la consolidación sugerida por carrier+país, y la
distinción B2B/B2C de "Restricciones de la empresa").

## Dónde vive el código

```
services/knowledge-api/
  memory_store.py       # Backend Redis: MemoryEntry, read/write/delete/list_memory_keys(),
                         #   + enforce_memory_capacity() (Consolidación y Limpieza: TTL + tope de entradas)
  memory_proposal.py     # Auto-evaluación: evaluate_for_memory_proposal() -- heurística determinista;
                         #   extract_country() ahora deriva el país del carrier conocido, no solo del texto
  memory_decision.py     # Clasificación de la resolución: classify_memory_decision() -- approved/rejected/edited
  memory_audit.py        # Registro auditable: record_memory_decision()/read_audit_log() (JSONL)
  agent_graph.py          # 3 nodos nuevos: retrieve_memory, propose_memory, resolve_pending_memory_proposal
  schemas.py               # + QueryRequest.thread_id, + AgentQueryResponse (con thread_id)
  routers/agent.py         # reenvía/devuelve thread_id

tests/pipelines/
  test_agent_memory.py    # 33 tests: memory_store (incl. TTL/capacidad), memory_proposal, memory_decision,
                           #   integración con el grafo
  test_agent_graph.py     # actualizado: node_order incluye retrieve_memory/propose_memory en cada ruta

data/eval/
  agent-memory-audit.jsonl   # generado en tiempo de ejecución, append-only (no comiteado, igual que agent-traces/)
```

## Cómo correrlo

```bash
cd services/knowledge-api
uv sync
# Redis real (ya usado por services/incidents-api) -- AGENT_MEMORY_REDIS_URL en .env, o cae a REDIS_URL
uv run pytest ../../tests/pipelines/test_agent_memory.py -q    # 27 tests, con fakeredis, sin Redis real
```

## Checklist de la entrega

- [x] **Backend de memoria persistente elegido y documentado por
  escrito**: Redis (`memory_store.py`) — ya corre en este repo
  (`services/incidents-api`, broker de Celery); los hechos que el agente
  necesita recordar (`CONTEXT8.md`) son de baja cardinalidad y se
  consultan por clave exacta (`carrier:país`, `client:nombre`), nunca por
  similitud semántica — una VectorDB resolvería un problema que esta
  memoria no tiene. Justificación completa en el docstring del módulo, no
  solo en este documento.
- [x] **Nunca en las colecciones RAG de la empresa**: namespace Redis
  separado (`agent_memory:*`), nunca `trackflow_knowledge` (Qdrant) —
  verificado explícitamente (`test_memory_entry_is_isolated_from_qdrant_rag_namespace`).
- [x] **Interfaz explícita de lectura/escritura**: `read_memory()`/
  `write_memory()` son los ÚNICOS puntos de acceso — el agente nunca
  concatena memoria cruda al system prompt. Lado de lectura:
  `agent_graph.py::retrieve_memory` (nodo nuevo, corre siempre, antes de
  cualquier ruta). Lado de escritura: solo
  `resolve_pending_memory_proposal`, solo tras aprobación/edición explícita
  del usuario.
- [x] **Las categorías memorizables/prohibidas corresponden exactamente a
  `CONTEXT-company.md`** (`CONTEXT8.md` en este repo), no una versión
  genérica: `memory_proposal.py` reconoce las 3 categorías permitidas
  (regla de carrier, contexto de incidente recurrente, preferencia de
  cliente B2B) y filtra explícitamente las 3 prohibidas (dirección/ruta
  interna de cliente final, incidente puntual sin patrón, contrato en
  negociación) — un candidato que dispara el patrón permitido pero también
  el prohibido NUNCA se propone (`test_eval_forbidden_content_never_proposed_even_if_pattern_matches`).

### Auto-evaluación y Propuesta de Memoria

- [x] **Auto-evaluación con criterio explícito tras cada interacción
  relevante**: `propose_memory` (nodo nuevo, corre después de
  `generate`/`no_context`) llama a `evaluate_for_memory_proposal(question,
  answer)` — nunca simplemente "siempre".
- [x] **Una sola llamada, campo adicional en la salida, no una segunda
  arquitectura**: `propose_memory` corre en el mismo turno/grafo que
  generó la respuesta, no dispara una llamada nueva al modelo ni un agente
  separado. Documentado explícitamente en `memory_proposal.py` como el
  punto de inyección para la versión real (salida estructurada de
  `GENERATION_MODEL`) el día que haya credenciales de 4Geeks.
- [x] **Descarta la mayoría de interacciones, con ≥3 ejemplos
  documentados**: los 3 ejemplos literales de `CONTEXT8.md` ("¿Dónde está
  el paquete con tracking XJ4471?", "Perfecto, ya quedó resuelto.",
  "Tradúceme esto al inglés") están en
  `test_eval_examples_that_should_not_generate_a_proposal`, más los 4
  ejemplos de contenido prohibido de `CONTEXT8.md` (dirección de cliente,
  ruta interna, incidente puntual, contrato en negociación).
- [x] **La propuesta se hace dentro de la misma respuesta, nunca escribe a
  memoria en este paso**: `propose_memory` solo guarda
  `pending_memory_proposal` en el estado y agrega la pregunta al final de
  `answer` — `write_memory()` nunca se llama desde este nodo (verificado:
  `recorded_writes == []` en `test_turn_proposes_memory_within_the_same_answer`).

### Confirmación del Usuario y Registro Auditable

- [x] **El mensaje siguiente se evalúa contra la propuesta pendiente, con
  clasificación explícita, no `"sí" in mensaje`**: `classify_memory_decision()`
  usa patrones de palabra completa — probado explícitamente con un caso que
  un `in` ingenuo clasificaría mal (`test_naive_substring_match_would_have_misclassified_this`,
  "No, no sé **si** eso es **así**").
- [x] **Una sola propuesta pendiente a la vez**: garantizado por
  construcción del grafo (`propose_memory` solo se alcanza después de que
  `resolve_pending_memory_proposal`, si corrió este turno, ya limpió
  `pending_memory_proposal`) — verificado con un caso límite real: el
  usuario aprueba la propuesta pendiente Y trae una observación memorable
  nueva en el mismo mensaje; al final solo queda UNA propuesta pendiente,
  la nueva (`test_only_one_pending_proposal_at_a_time`).
- [x] **Cambio de tema sin sí/no claro → descartada por defecto**:
  `classify_memory_decision()` devuelve `"rejected"` para cualquier mensaje
  que no dispare un patrón de aprobación/edición/rechazo explícito —
  nunca se asume aprobación (`test_decision_defaults_to_rejected_on_topic_change`).
- [x] **Cada decisión queda registrada de forma auditable, aprobada o
  no**: `memory_audit.py::record_memory_decision()` — JSONL append-only en
  `data/eval/agent-memory-audit.jsonl` (thread_id, propuesta completa,
  resultado, mensaje que la originó, timestamp). Probado para ambos
  resultados: aprobada (`test_pending_proposal_survives_to_the_next_turn_and_gets_approved`)
  y rechazada (`test_pending_proposal_rejected_is_not_written_but_is_audited`)
  — la auditoría se registra en los dos casos, solo el `write_memory` es
  condicional.
- [x] **La conversación sigue con normalidad después de resolver,
  incluyendo pregunta nueva en el mismo mensaje**: `resolve_pending_memory_proposal`
  siempre continúa hacia `classify_intent` (nunca corta a `END`) — el
  mismo test de "una sola propuesta pendiente" lo confirma: el mensaje que
  resuelve la propuesta anterior también genera una propuesta nueva, lo
  que solo es posible si el grafo completó su recorrido normal
  (`classify_intent` → ... → `generate` → `propose_memory`) después de
  resolver.

### Consolidación y Limpieza

- [x] **Mecanismo de consolidación que evite que la memoria crezca sin
  control**: dos mecanismos reales combinados en `memory_store.py`, no
  simulados —
  1. Cada `write_memory()` consolida por `key` (upsert, no apila —
     ya cubierto arriba, "Backend de memoria persistente").
  2. `enforce_memory_capacity()` (disparada automáticamente por
     `write_memory()`, `max_entries=200` por defecto): si el total de
     entradas supera el máximo, descarta las de `updated_at` más antiguo
     hasta volver al límite — "descartar entradas de baja relevancia"
     operacionalizado como "la que nadie volvió a confirmar/corregir en
     más tiempo", sin necesitar un modelo real de relevancia. Probado con
     5 entradas y un tope de 3: las 2 más viejas se descartan, las 3 más
     recientes sobreviven (`test_enforce_memory_capacity_evicts_oldest_updated_entries_beyond_the_cap`),
     y que no hace nada por debajo del tope
     (`test_enforce_memory_capacity_is_a_noop_under_the_cap`).
- [x] **Política de expiración documentada, con el porqué**: TTL nativo de
  Redis (`MEMORY_TTL_SECONDS`, 180 días por defecto) en cada
  `write_memory()` — los hechos que esta memoria guarda son correcciones
  *vigentes*, no verdades permanentes (un carrier puede volver a cambiar
  su cobertura sin que nadie se lo informe de nuevo al agente); 180 días
  sobrevive una temporada operativa completa pero fuerza re-confirmación
  periódica. Una reconfirmación/edición renueva el TTL
  (`test_write_memory_renews_ttl_on_reconfirmation`) — una regla que se
  sigue usando y corrigiendo nunca expira por accidente. Razonamiento
  completo en el docstring de `memory_store.py`, sección "Consolidación y
  Limpieza".

### Evidencia

- [x] **Dos ciclos completos del flujo documentados**: ver "Cómo se
  verificó" #9 más abajo — uno donde la propuesta se aprueba y se refleja
  en una interacción futura (en un hilo nuevo, sin relación con el que la
  propuso), y otro donde se rechaza y la memoria permanece sin cambios
  (la interacción futura NO refleja nada). Los dos corridos de punta a
  punta vía HTTP real (`TestClient` contra `POST /agent/query`) con Redis
  real, no simulados ni solo a nivel de test unitario.

## Cómo se verificó

Sin credenciales de 4Geeks para una auto-evaluación/clasificación real por
LLM (mismo límite que `classify_intent` en Hito 7), pero con infraestructura
real donde sí la hay (Redis real, HTTP real, checkpointer real):

1. **Verificación arquitectónica previa, no asumida**: antes de diseñar el
   flujo de "propuesta pendiente sobrevive al turno siguiente", se probó
   con un grafo mínimo de LangGraph que el checkpointer efectivamente
   conserva un campo del estado entre dos `ainvoke()` **separados** sobre
   el mismo `thread_id` cuando el segundo input no lo toca — confirmado
   antes de escribir una sola línea de `agent_graph.py` para esta entrega.
2. **Bug real encontrado y corregido — el checkpointer nunca sobrevivía
   entre requests HTTP**: al verificar el punto anterior contra el
   `run_agent()` YA EXISTENTE (de Hito 7), que hasta ahora nadie había
   necesitado, se descubrió que cada llamada sin un `checkpointer`
   explícito pasaba `None` a `build_graph()`, que creaba un `MemorySaver()`
   **nuevo** en cada corrida — nada sobrevivía entre dos requests
   `POST /agent/query` separados con el mismo `thread_id`, a pesar de que
   el docstring de Hito 7 ya afirmaba soporte de checkpointing "para
   retomar una corrida". Era cosmético hasta esta entrega; con memoria
   (una propuesta pendiente debe sobrevivir al turno siguiente, que en
   producción es otro request HTTP) se vuelve un bloqueante real.
   Corregido con `_DEFAULT_CHECKPOINTER`, un único `MemorySaver` a nivel
   de módulo compartido entre llamadas.
3. **Bug real encontrado y corregido — `retrieve_memory` tumbaba el turno
   completo si Redis estaba caído**: el primer intento no envolvía
   `read_fn()` en manejo de errores — una pregunta de RAG que de pura
   casualidad mencionara el nombre de un carrier (p. ej. "¿UPS Ground
   cubre Los Ángeles?") hacía fallar el turno COMPLETO con un
   `redis.exceptions.ConnectionError` crudo si Redis no estaba disponible,
   en vez de simplemente responder sin el contexto de memoria. Encontrado
   corriendo la suite de tests por primera vez sin mockear `read_memory_fn`
   en algunos tests (el error real de conexión, no uno inventado).
   Corregido con un `try/except Exception` alrededor de la lectura, mismo
   criterio que usan las tools del MCP Server ante un fallo de red.
4. **Bug real encontrado y corregido — `None` en el stream de "updates" de
   LangGraph**: `propose_memory` puede legítimamente devolver `{}` (nada
   memorable), y se descubrió corriendo el primer test de memoria que
   LangGraph representa un nodo sin cambios de estado como `None` (no
   `{}`) en `stream_mode="updates"` — `run_agent()` crasheaba con
   `TypeError: 'NoneType' object is not iterable` al intentar hacer
   `final_state.update(None)`. Ningún nodo anterior (Hito 7) había
   devuelto nunca un `{}` real, así que este caso nunca se había disparado
   antes. Corregido normalizando `partial_state = partial_state or {}`
   antes de usarlo.
5. **Bug real encontrado y corregido — `_route_after_retrieve` ignoraba
   `memory_context`**: un test end-to-end (pregunta sobre un carrier con
   una entrada de memoria ya aprobada, pero sin contexto RAG ni tool)
   reveló que el grafo enrutaba a `no_context` en vez de `generate` —
   `_route_after_retrieve` solo miraba `context`/`tool_result`, nunca
   `memory_context`. El test falló con la respuesta genérica de "no tengo
   información" en vez del hecho recordado, confirmando el bug antes de
   corregirlo.
6. **Bug real encontrado y corregido — propuestas repetidas en loop**:
   corriendo el flujo completo de punta a punta vía HTTP real (ver punto
   8), una memoria ya aprobada y reutilizada en una respuesta futura
   **se volvía a proponer** en esa misma respuesta. Causa:
   `evaluate_for_memory_proposal` evaluaba `question + answer` combinados,
   y `answer` ahora podía contener el propio hecho de memoria inyectado
   por `retrieve_memory` — el patrón de "regla de carrier corregida"
   volvía a dispararse sobre su propio eco. Corregido evaluando
   **solo** `question` (el mensaje del usuario), nunca la respuesta del
   agente — documentado en el docstring de la función con el bug real que
   motivó la decisión.
7. **`tests/pipelines/test_agent_memory.py`, 27 tests, `fakeredis`
   (misma API que `redis-py`) para los tests unitarios de
   `memory_store.py`**: lectura/escritura/consolidación/aislamiento del
   namespace Qdrant, los 3+3+4 ejemplos de auto-evaluación de `CONTEXT8.md`,
   la clasificación de decisión (incluido el caso que un `"sí" in mensaje`
   clasificaría mal), y 5 tests de integración completa con el grafo
   (`agent_graph.MemorySaver()` real, no fakeado) cubriendo: propuesta en
   el mismo turno, aprobación en el turno siguiente, rechazo auditado sin
   escritura, una sola propuesta pendiente a la vez, y lectura de memoria
   inyectada en la generación.
8. **Flujo completo verificado de punta a punta vía HTTP real, con Redis
   real** (contenedor Docker `redis:7-alpine`, el mismo que ya corría para
   la validación del MCP Server) — 3 requests reales a
   `TestClient.post("/agent/query", ...)`, reutilizando `thread_id` entre
   el primero y el segundo:
   - Turno 1: "En realidad SEUR ya no cubre esa zona rural de Zaragoza..."
     → propone memoria dentro de la misma respuesta.
   - Turno 2 (mismo `thread_id`): "Sí, guárdalo." → aprobada, escrita en
     Redis de verdad.
   - Turno 3 (hilo **nuevo**, sin relación con 1-2): "¿SEUR cubre la ruta
     rural de Zaragoza?" → `retrieve_memory` encuentra la entrada real en
     Redis y la inyecta como contexto — la respuesta trae el hecho
     recordado, sin volver a proponerlo (bug 6, ya corregido).
9. **`tests/pipelines/test_agent_graph.py` (10 tests, Hito 7) actualizado,
   no roto**: cada `node_order` esperado se actualizó para incluir
   `retrieve_memory`/`propose_memory` en las rutas que corresponde (nunca
   después de `tool_failed`) — mismas aserciones de fondo, ninguna lógica
   de test cambiada. `test_rag.py` (17 tests) no se tocó. Los tres
   archivos, corridos cada uno en su propia invocación de `pytest` (patrón
   ya establecido por la colisión conocida de `sys.modules['rag']`, ver
   `Pasos/rag-knowledge-base-fase1.md` "Pendiente" #10): `17 + 10 + 27 = 54
   passed`.
10. **`QueryRequest`/`AgentQueryResponse` extendidos para que el flujo sea
    alcanzable vía HTTP, no solo a nivel de grafo**: se descubrió, al
    intentar el smoke test de punta a punta (#8), que `routers/agent.py`
    nunca le pasaba `thread_id` a `run_agent()` ni lo devolvía en la
    respuesta — cada request HTTP generaba un hilo nuevo sin que el
    cliente pudiera continuarlo, haciendo que toda la mecánica de
    "propuesta pendiente" fuera inalcanzable desde fuera del proceso
    aunque funcionara perfecto a nivel de `run_agent()`/tests. Corregido
    agregando `thread_id` opcional a `QueryRequest` y un nuevo
    `AgentQueryResponse` (con `thread_id` obligatorio) solo para
    `/agent/query` -- `QueryResponse` (compartido con `/knowledge/query`,
    sin estado) no se tocó.
11. **Bug real encontrado y corregido mientras se documentaba la
    "Evidencia" (#12) — el país se adivinaba del texto, no del
    carrier**: el primer intento de `extract_country()` solo buscaba
    nombres de ciudad ("zaragoza", "españa") en el texto libre. Al correr
    el Ciclo A de evidencia con una pregunta real sobre "Nacex" y "esa
    zona rural de **Aragón**" (sin mencionar "Zaragoza"), la clave
    consolidada salió `"Nacex:USA"` — incorrecta: Nacex es, según
    `docs/company-knowledge-base/trackflow-carrier-coverage.es.md`, un
    carrier exclusivo de España. Encontrado inspeccionando la respuesta
    real del primer intento (`"Corrección de regla de asignación para
    Nacex (USA)"`), no adivinado de antemano. Corregido con un mapa
    `_CARRIER_COUNTRY` (país real de cada uno de los 8 carriers conocidos,
    tomado del documento de cobertura real) — `extract_country()` ahora
    deriva el país del carrier cuando lo conoce (confiable, nunca
    ambiguo) y solo cae al heurístico de texto para `"DHL Express"` sin
    calificar (el único nombre que opera en ambos países). Aplicado
    también en `agent_graph.py::retrieve_memory` para que la clave de
    lectura y de escritura usen siempre la misma lógica. Test de
    regresión: `test_proposal_country_comes_from_the_carrier_not_just_city_names_in_the_text`.
12. **Evidencia: los dos ciclos completos, corridos de punta a punta vía
    HTTP real con Redis real** (mismo contenedor `redis:7-alpine` de la
    validación del MCP Server), Redis limpio antes de empezar
    (`agent_memory:*` vacío):

    **Ciclo A — aprobada, se refleja en una interacción futura:**
    ```
    A.1 POST /agent/query {"question": "En realidad Nacex ya no cubre esa
        zona rural de Aragon, hay que usar el carrier local desde el mes
        pasado."}
    -> {"answer": "No tengo información sobre eso en la base de
        conocimiento de TrackFlow.\n\n¿Querés que recuerde esto para la
        próxima? Corrección de regla de asignación para Nacex (Spain).",
        "thread_id": "2b275846-..."}

    A.2 POST /agent/query {"question": "Sí, guárdalo.",
        "thread_id": "2b275846-..."}  (mismo hilo que A.1)
    -> {"answer": "No tengo información sobre eso en la base de
        conocimiento de TrackFlow.", "thread_id": "2b275846-..."}
        (Redis real: agent_memory:Nacex:Spain escrito, TTL ~180 dias)

    A.3 POST /agent/query {"question": "¿Nacex cubre la ruta rural de
        Aragón?"}  (hilo NUEVO, sin relación con A.1/A.2)
    -> {"answer": "En realidad Nacex ya no cubre esa zona rural de
        Aragon, hay que usar el carrier local desde el mes pasado.",
        "thread_id": "cd1371f3-..."}
        -- el hecho aprobado en A.2 aparece en una conversación
        completamente distinta, y NO se vuelve a proponer (bug 6 de la
        entrega anterior, confirmado corregido acá también).
    ```

    **Ciclo B — rechazada, la memoria permanece sin cambios:**
    ```
    B.1 POST /agent/query {"question": "En realidad DHL Express USA ya no
        cubre esa zona rural, hay que usar el carrier local desde el mes
        pasado."}
    -> {"answer": "No tengo información sobre eso en la base de
        conocimiento de TrackFlow.\n\n¿Querés que recuerde esto para la
        próxima? Corrección de regla de asignación para DHL Express USA
        (USA).", "thread_id": "5ef3eb79-..."}

    B.2 POST /agent/query {"question": "No, eso no es correcto.",
        "thread_id": "5ef3eb79-..."}  (mismo hilo que B.1)
    -> {"answer": "No tengo información sobre eso en la base de
        conocimiento de TrackFlow.", "thread_id": "5ef3eb79-..."}
        (Redis real: NUNCA se escribió agent_memory:"DHL Express USA":USA)

    B.3 POST /agent/query {"question": "¿DHL Express USA cubre esa ruta
        rural?"}  (hilo NUEVO)
    -> {"answer": "No tengo información sobre eso en la base de
        conocimiento de TrackFlow.", "thread_id": "b40dd26e-..."}
        -- sin rastro del hecho rechazado, la memoria no cambió.
    ```

    Confirmado además inspeccionando Redis directamente después de los dos
    ciclos: `agent_memory:*` solo tenía la clave `Nacex:Spain` (la
    aprobada) -- ninguna clave para DHL Express (la rechazada). El audit
    log (`data/eval/agent-memory-audit.jsonl`) trae las dos decisiones:
    `approved` para `Nacex:Spain` y `rejected` para `DHL Express USA:USA`,
    cada una con su `triggering_message` y `timestamp` reales.

## Decisiones de implementación no cubiertas por la guía genérica

- **Redis, namespace de claves `agent_memory:*`, consolidado por
  `carrier:país`**: ver justificación completa en el docstring de
  `memory_store.py` y el checklist arriba.
- **`memory_proposal.py`/`memory_decision.py` como heurísticas
  deterministas, mismo patrón que `classify_intent`**: sin credenciales de
  4Geeks, no hay forma confiable y offline de probar una versión real por
  LLM. El punto de inyección (`evaluate_memory_fn`/`decide_memory_fn` en
  `build_graph()`) ya deja lista la sustitución.
- **`retrieve_memory` corre para TODA ruta, no solo cuando el usuario
  pregunta explícitamente por un carrier**: así es como una corrección
  pasada mejora silenciosamente una respuesta futura sin que el usuario
  tenga que repetirla — exactamente el problema que `CONTEXT8.md` describe
  (los 15 agentes de soporte corrigiendo las mismas reglas una y otra
  vez). Degrada a "sin memoria" ante cualquier fallo (bug 3 arriba), nunca
  bloquea una ruta que no depende de memoria.
- **`propose_memory` nunca corre después de `tool_failed`**: un fallo de
  red/timeout no produjo ninguna información nueva que valga la pena
  recordar — proponerla ahí sería ruido, no una mejora real del agente.
- **`write_memory`/`record_memory_decision` envueltos en `try/except`
  dentro de `resolve_pending_memory_proposal`**: un fallo de Redis al
  intentar escribir (ej. justo cuando el usuario aprueba) no debe
  reportarse como `"approved"` en la auditoría si el write de verdad
  falló -- el outcome auditado pasa a `"approved_write_failed:<detalle>"`,
  honesto en vez de silenciosamente incorrecto.
- **`AgentQueryResponse` separado de `QueryResponse`, no un campo
  `thread_id` opcional compartido**: `/knowledge/query` (Fase 3, Hito 7)
  es intencionalmente sin estado/sin concepto de hilo — forzarle un
  `thread_id` en la respuesta habría sido incoherente con su propio
  diseño, aunque técnicamente no rompiera nada (el campo en el
  `QueryRequest` sí se comparte, porque ahí es inofensivo que
  `/knowledge/query` simplemente lo ignore).
- **Desalojo por `updated_at` más antiguo, no por `created_at` ni LRU de
  lecturas**: `enforce_memory_capacity()` usa cuándo se **confirmó/corrigió**
  por última vez una entrada, no cuándo se creó ni cuándo se **leyó** por
  última vez. Un hecho viejo que se sigue reconfirmando (`write_memory`
  renueva `updated_at`) se mantiene fresco; uno que nadie corrige hace
  tiempo es el candidato más razonable a estar desactualizado, sin
  necesitar rastrear accesos de lectura (más estado, más complejidad, para
  una señal que `updated_at` ya aproxima razonablemente).
- **`_CARRIER_COUNTRY` como mapa explícito, no seguir ampliando el
  heurístico de texto con más nombres de ciudad**: el bug real de Aragón
  (ver "Cómo se verificó" #11) mostró que cualquier heurístico de texto
  tiene huecos (¿y "Teruel"? ¿y "Huesca"?) -- derivar el país del carrier
  mismo es la fuente de verdad correcta siempre que el carrier sea
  conocido, y es exactamente la misma información que ya vive en
  `docs/company-knowledge-base/trackflow-carrier-coverage.es.md`.

## Pendiente / siguientes pasos

1. **Sección "Decisiones de Diseño" del checklist no implementada**: la
   segunda captura de pantalla terminaba justo en ese encabezado
   ("Como parte del reto, tu implementación debe resolver — sin que se te
   diga explícitamente en un checklist — las siguientes decisiones:"), sin
   ningún bullet visible debajo — no se pudo resolver contenido que no se
   compartió. Si esta sección pide justificar decisiones de diseño no
   cubiertas por un checklist explícito, buena parte probablemente ya está
   cubierta por la sección "Decisiones de implementación" de este mismo
   documento -- pero falta confirmar contra el contenido real.
2. **Sin credenciales reales de 4Geeks** para auto-evaluación/clasificación
   de decisión por LLM — mismo límite que `classify_intent` desde Hito 7.
   Los puntos de inyección (`evaluate_memory_fn`, `decide_memory_fn`) ya
   están listos.
3. **`MemorySaver` en memoria del proceso** (mismo límite de Hito 7,
   ahora más visible): `pending_memory_proposal` no sobrevive un reinicio
   de `knowledge-api` — para eso haría falta `SqliteSaver`/`PostgresSaver`,
   no incluido en esta entrega.
4. **`extract_carrier`/`_CLIENT_DESCRIPTOR_RE` son heurísticas de texto,
   no un registro real de carriers/clientes**: un carrier mencionado con
   una grafía distinta a las 8 conocidas (ver `docs/company-knowledge-base/trackflow-carrier-coverage.es.md`)
   o un nombre de cliente ambiguo no se reconocerían. Mismo tipo de límite
   documentado que `classify_intent`.
5. **No se agregó UI en `uis/backoffice` para ver/gestionar memoria
   directamente** (listar entradas, borrar una regla vieja a mano) — el
   checklist de esta entrega no lo pide explícitamente; `list_memory_keys()`/
   `delete_memory()` ya existen como base si se pidiera después.
