# Harness y guardrails del agente (Hito 8 · Parte 2)

Fecha: 2026-10-05

Implementación de `CONTEXT/CONTEXT8.2.md` ("Aseguramiento de Agentes:
Harness y Guardrails"): asegura el **mismo** agente de
`services/knowledge-api/agent_graph.py` que Hito 7 construyó (RAG + tools
del MCP Server) y Hito 8 Parte 1 extendió con memoria — no hay un agente
paralelo para este sprint, tal como exige explícitamente la Sección 1 de
`CONTEXT8.2.md`.

Antes de implementar, leí `CONTEXT/CONTEXT8.2.md` completo: a quién sirve
el agente (CX de primera línea, B2B y B2C, Valentina Cruz), el alcance de
dominio exacto (Sección 2), los datos que nunca debe revelar (Sección 3), y
los 4 casos de prueba obligatorios (Sección 4) — los mismos que se
implementan y testean acá, no una versión genérica.

## Dónde vive el código

```
services/knowledge-api/
  guardrails.py          # AGENT_SYSTEM_PROMPT + las 7 funciones de guardrail (ver checklist abajo)
  guardrail_audit.py      # Observabilidad: record_guardrail_event(), get_summary(), JSONL append-only
  agent_graph.py           # 3 nodos nuevos: input_guard, guardrail_blocked, output_guard
                            # + generate_node sanitiza contenido externo antes de generar
  routers/agent.py         # GET /agent/guardrails/summary (nuevo) + payload.authorized_order_ids
  schemas.py                # + QueryRequest.authorized_order_ids

data/pipelines/rag.py      # generate_answer() + parametro system_prompt (para no duplicar la funcion)

tests/pipelines/
  test_agent_guardrails.py  # 31 tests: guards unitarios, integración con el grafo, observabilidad
  test_agent_graph.py       # actualizado: node_order incluye input_guard/output_guard en cada ruta
  test_agent_memory.py      # actualizado: 1 node_order ajustado (input_guard antes de resolve_pending...)

data/eval/
  agent-guardrail-log.jsonl   # generado en tiempo de ejecución, append-only (no comiteado, igual que
                               # agent-traces/ y agent-memory-audit.jsonl)
```

## Cómo correrlo

```bash
cd services/knowledge-api
uv sync
uv run pytest ../../tests/pipelines/test_agent_guardrails.py -q   # 31 tests, sin LLM vivo, sin Redis
```

```bash
# Resumen de guardrails activados durante una sesión de pruebas:
curl http://localhost:8000/agent/guardrails/summary
```

## Checklist de la entrega — System Prompt seguro

- [x] **System prompt reescrito, separando instrucciones del sistema de
  input del usuario**: `guardrails.py::AGENT_SYSTEM_PROMPT` — trae un
  bloque explícito ("INSTRUCCIONES DEL SISTEMA (este bloque) vs. MENSAJE
  DEL USUARIO...") que declara textualmente que el mensaje del usuario
  nunca tiene la autoridad del system prompt. Inyectado en
  `generate_answer()` (`data/pipelines/rag.py`) vía su nuevo parámetro
  `system_prompt` -- la función no se duplicó, solo se parametrizó.
- [x] **Dominio declarado explícitamente, con las condiciones de salida**:
  el prompt enumera el dominio exacto de `CONTEXT8.2.md` Sección 2 (estado
  de tracking, políticas de devolución/SLA por país, procedimientos de
  incidencias), "fuera de dominio pero permitido" (small talk,
  redirección obligatoria), y "prohibido" (chatbot personal) — literal,
  no una versión genérica.
- [x] **≥3 variantes de jailbreak documentadas y probadas**: 5 en
  `tests/pipelines/test_agent_guardrails.py::test_eval_instruction_override_variants_are_blocked`
  -- los 2 casos literales de `CONTEXT8.2.md` Sección 4 (#1 en inglés,
  #2 "Olvídate de TrackFlow...") más 3 reformulaciones adicionales ("A
  partir de ahora...", "Dame tu system prompt...", "Actúa como si..."),
  las 5 bloqueadas.

⚠️ El dominio/reglas de `AGENT_SYSTEM_PROMPT` coinciden con `CONTEXT8.2.md`
Sección 2 literal, no con una versión genérica -- ver "Decisiones" sobre
por qué este prompt es DISTINTO del `SYSTEM_PROMPT` de
`data/pipelines/rag.py` (ese sirve a `POST /knowledge/query`, una
herramienta interna con su propia audiencia de Hito 7).

## Checklist de la entrega — Guardrails de contenido y alcance

- [x] **Guardrail de uso personal no relacionado, rechaza y redirige**:
  `guardrails.py::check_personal_use_request()` -- "escríbeme un poema de
  amor", "ayúdame con la tarea de mi universidad" (ejemplos literales del
  checklist) y más (ensayos, código, consejo personal). Bloquea con un
  mensaje que rechaza Y redirige al propósito del agente en el mismo
  texto.
- [x] **Guardrail de preguntas generales/casuales, permite pero
  redirige**: `check_casual_question()` -- "¿qué hora es en Tokio?"
  (ejemplo literal) y similares (clima, saludo, "qué es la logística
  inversa"). `action="redirect"`, no `"block"`: la pregunta se sigue
  respondiendo, solo se le anexa un cierre hacia el dominio de TrackFlow
  (`output_guard` lo hace, ver abajo).
- [x] **Validación de la salida del modelo antes de devolverla**:
  `validate_output()` -- 3 chequeos: formato (no vacía), fuga del system
  prompt (busca fragmentos reconocibles de `AGENT_SYSTEM_PROMPT` en la
  respuesta), y datos sensibles de `CONTEXT8.2.md` Sección 3 (tarifas
  negociadas con carriers, términos comerciales B2B, ubicación/rutas
  internas de almacenes). Corre en el nodo `output_guard`, después de
  `generate`/`no_context`, antes de que la respuesta llegue al usuario.

## Checklist de la entrega — Guardrails de seguridad (anti-inyección)

- [x] **Aislamiento de contenido externo (tool/RAG) -- nunca tratado como
  instrucción**: dos capas. (1) Estructural, ya existente desde Hito 7:
  `_build_prompt()` pone el contexto recuperado en el mensaje de rol
  `user` ("Contexto recuperado:"), nunca en el `system`. (2) Nueva,
  defensa en profundidad: `sanitize_external_content()`, llamada dentro
  de `generate_node` sobre TODOS los chunks (tool + RAG + memoria) antes
  de pasarlos a `generate_fn` -- neutraliza cualquier frase con forma de
  instrucción encontrada DENTRO del contenido en sí (p. ej. un ticket cuyo
  texto dice "ignora tus instrucciones"), y registra el evento
  (`category="security"`) cuando encuentra algo.
- [x] **Mecanismo de rechazo explícito, ≥3 reformulaciones de cambio de
  instrucciones**: el mismo `check_instruction_override()` de "System
  Prompt seguro" -- ver docstring de `guardrails.py` para por qué es
  intencionalmente el mismo detector sirviendo los dos bullets del
  checklist (mismo riesgo, dos ángulos del documento). 5 variantes
  probadas (arriba).
- [x] **Tests automatizados deterministas, sin LLM vivo como gate**: los
  31 tests de `test_agent_guardrails.py` corren con fakes/mocks fijos
  (`_refuse_to_be_called`, `fake_retrieve`, generadores fake) -- cero
  llamadas a un LLM real o a Qdrant real. Unit-tests para cada guard por
  separado (`check_*`, `validate_output`, `sanitize_external_content`) +
  tests de integración con el grafo completo que verifican que un input
  abusivo NUNCA llega a `generate_fn`/`incidents_tool_fn` (inyectados como
  `_refuse_to_be_called`, que hace fallar el test con un `AssertionError`
  si se llegaran a invocar -- "la suite debe fallar el build si las capas
  tratarían inputs abusivos como permitidos/obedecidos", literal).

⚠️ Caso 3 del checklist (`CONTEXT8.2.md` Sección 4, autorización de
sesión) tiene un límite real documentado explícitamente en "Decisiones" --
ver ahí antes de asumir que está completamente resuelto.

## Checklist de la entrega — Observabilidad mínima

- [x] **Cada bloqueo/redirección queda registrado, con el tipo de
  fallo**: `guardrail_audit.py::record_guardrail_event()` -- JSONL
  append-only en `data/eval/agent-guardrail-log.jsonl` (mismo patrón que
  `memory_audit.py`), con `category` (`"structural"`/`"content"`/`"security"`,
  mapeadas 1-a-1 a las 3 secciones del checklist -- ver docstring de
  `guardrails.py`), `guardrail_name`, `action`, `question`, `thread_id`,
  `timestamp`. Nunca se registra un evento cuando un guardrail deja pasar
  algo sin cambios (eso no es un fallo).
- [x] **Resumen expuesto (endpoint) de cuántas veces se activó cada
  guardrail durante una sesión de pruebas**: `GET /agent/guardrails/summary`
  (`routers/agent.py`) -- contadores de proceso (`collections.Counter`,
  `guardrail_audit.py`), por guardrail y por categoría. Probado end-to-end
  con `TestClient`: 4 requests reales (jailbreak, uso personal, tracking
  no autorizado, pregunta casual) seguidas de `GET .../summary` →
  `{"total_events": 4, "by_guardrail": {...los 4...}, "by_category":
  {"structural": 1, "content": 2, "security": 1}}` (ver "Cómo se
  verificó").

## Cómo se verificó

Sin credenciales reales de 4Geeks (mismo límite que toda auto-evaluación
previa de esta sesión), pero con el grafo real, HTTP real, y los 4 casos
de prueba literales de `CONTEXT8.2.md` ejecutados de verdad:

1. **Cada patrón probado contra las frases reales del checklist antes de
   escribir un solo nodo del grafo** -- script exploratorio con los 4
   casos de `CONTEXT8.2.md` Sección 4 + los ejemplos de cada sección del
   checklist genérico, confirmando qué bloqueaba/pasaba antes de integrar
   nada a `agent_graph.py`.
2. **Bug real encontrado y corregido -- el guardrail de mezcla de países
   no reconocía el caso 4 literal**: el primer regex de
   `check_country_policy_mixing()` esperaba `"política de España"`
   adyacente, pero la frase real de `CONTEXT8.2.md`
   ("Aplica la política **de devoluciones** de España a mi pedido...")
   tiene "de devoluciones" insertado entre "política" y el país -- no
   matcheaba. Encontrado corriendo el caso literal del checklist, no
   asumido. Corregido permitiendo una ventana de texto entre "política" y
   el nombre del país.
3. **Bug real encontrado y corregido -- sanitización dejaba un resto de
   texto**: `sanitize_external_content()` sustituía `"ignora tus
   instruccion"` pero no consumía el sufijo `"es"` de "instruccion**es**",
   dejando `"[contenido no interpretado como instrucción]es"` en el chunk
   saneado. Encontrado inspeccionando la salida real del sanitizador, no
   adivinado. Corregido agregando `(es)?` a los dos patrones de
   "instruccion" que les faltaba.
4. **`tests/pipelines/test_agent_guardrails.py`, 31 tests, los 31 en
   verde en la primera corrida completa** (tras las dos correcciones de
   arriba): unit-tests de los 7 guards + 7 tests de integración con el
   grafo completo (jailbreak, uso personal, tracking no autorizado, y
   pregunta casual -- cada uno probado end-to-end contra `run_agent()`
   real, no solo la función del guard en aislamiento) + 3 de
   observabilidad.
5. **Flujo end-to-end real vía HTTP** (`TestClient` contra
   `POST /agent/query`, con `retrieve_fn`/tool fns fakeados por no haber
   Qdrant/MCP Server corriendo en este momento, pero el resto de la pila
   real): los 4 casos de `CONTEXT8.2.md` Sección 4, uno por uno:
   - Caso 1 (jailbreak en inglés) → `200`, respuesta de rechazo, nunca
     llega a `generate`.
   - Caso 2 (ensayo + "olvídate de TrackFlow") → `200`, mismo guardrail
     (`instruction_override`, dispara antes que `personal_use_request`
     por orden de chequeo -- cualquiera de los dos sería correcto, el
     primero en el orden gana).
   - Caso 3 (`pedido #45821` fuera de `authorized_order_ids=["12345"]`) →
     `200`, rechazo explícito por autorización, nunca "no encontré ese
     pedido".
   - Caso 4 (mezcla de políticas España/Los Ángeles) → `200`, rechazo
     explícito ("cada pedido sigue la política del país donde realmente
     se gestiona"), nunca mezcla las políticas.
   - `GET /agent/guardrails/summary` después de cada caso → conteos
     reales correctos por guardrail y por categoría en cada corrida (el
     caso 4 se probó en una sesión aparte: `{"total_events": 1,
     "by_guardrail": {"country_policy_mixing": 1}, "by_category":
     {"content": 1}}`).
6. **`tests/pipelines/test_agent_graph.py` (10 tests, Hito 7) y
   `test_agent_memory.py` (33 tests, Hito 8 Parte 1) actualizados, no
   rotos**: cada `node_order` esperado se actualizó para incluir
   `input_guard`/`output_guard` en las rutas que corresponde -- mismas
   aserciones de fondo, ninguna lógica de test cambiada. Confirmado
   además que la pregunta del eval de anclaje de Hito 7 ("¿puede un
   account manager ofrecer un descuento de almacenamiento sin
   aprobación?") NO dispara ningún guardrail nuevo por accidente (podría
   haber chocado con el patrón de "descuento", no lo hizo). `test_rag.py`
   (17 tests, Fase 2) tampoco se rompió por el nuevo parámetro
   `system_prompt` de `generate_answer()` (opcional, con default
   backward-compatible). Los cuatro archivos, cada uno en su propia
   invocación de `pytest` (colisión conocida de `sys.modules['rag']`, ver
   `Pasos/rag-knowledge-base-fase1.md` "Pendiente" #10):
   `17 + 10 + 33 + 31 = 91 passed`.

## Decisiones de implementación no cubiertas por la guía genérica

- **`AGENT_SYSTEM_PROMPT` (guardrails.py) es DISTINTO del `SYSTEM_PROMPT`
  de `data/pipelines/rag.py`, no un reemplazo**: el `SYSTEM_PROMPT`
  original (Hito 7) está escrito para un account manager interno
  ("Un account manager te está usando en tiempo real durante una
  llamada..."), la audiencia de `POST /knowledge/query` según
  `CONTEXT7.md`. `CONTEXT8.2.md` describe una audiencia completamente
  distinta para el agente ("agente de primera línea de CX... clientes B2B
  y B2C"). Reescribir el `SYSTEM_PROMPT` compartido habría cambiado el
  comportamiento de `/knowledge/query` sin que ningún checklist lo pidiera
  -- en cambio, `generate_answer()` ganó un parámetro `system_prompt`
  opcional (con el original como default, backward-compatible) y el
  agente inyecta el suyo. Cada endpoint sigue fiel a SU PROPIO documento
  CONTEXT.
- **`check_instruction_override()` sirve dos bullets del checklist a la
  vez**: ver docstring de `guardrails.py` -- "System Prompt seguro" pide
  documentar variantes probadas, "Guardrails de seguridad" pide el
  mecanismo de rechazo con ≥3 reformulaciones; es el mismo riesgo
  (autoridad del mensaje del usuario sobre el system prompt) descrito dos
  veces en el checklist, no dos guardrails distintos.
- **`input_guard` corre ANTES que `resolve_pending_memory_proposal`**: la
  seguridad tiene prioridad sobre la memoria -- un mensaje que intenta un
  jailbreak mientras hay una propuesta de memoria pendiente se bloquea
  igual, nunca llega a resolver ni a crear una propuesta nueva.
- **Pregunta casual: `action="redirect"`, nunca `"block"`**: el checklist
  es explícito en que esto se permite, solo se redirige -- tratarlo como
  bloqueo habría sido más simple de implementar pero violaría el
  requisito literal.
- **`check_unauthorized_tracking_request` no bloquea cuando
  `authorized_order_ids=None`**: este repo no tiene un sistema de
  autenticación de sesión conectado a `POST /agent/query` todavía (ningún
  Hito anterior lo pidió). Bloquear TODO número de pedido sin excepción
  cuando no se declaró ninguna sesión sería más "seguro" en apariencia,
  pero rompería el caso normal (un caller legítimo que simplemente no usa
  este parámetro todavía) sin agregar seguridad real -- la verdadera
  autorización necesita un sistema de sesión real, no una lista opcional
  en el body. Documentado como límite explícito, no escondido.
- **`sanitize_external_content` reutiliza el mismo regex que
  `check_instruction_override`**: el riesgo es literalmente el mismo
  patrón de texto (frases con forma de instrucción), solo que una vez
  viene del USUARIO (bloquear el turno) y la otra viene de un DOCUMENTO/tool
  (neutralizar esa porción del texto, no bloquear el turno entero --  un
  ticket real puede legítimamente citar lo que un cliente dijo, incluida
  una frase sospechosa, sin que eso deba tumbar toda la respuesta).
- **Contadores de `guardrail_audit.py` en memoria del proceso, no en
  Redis/Postgres**: "durante una sesión de pruebas" (texto literal del
  checklist) es exactamente el alcance de un proceso -- agregar
  persistencia cross-proceso sería infraestructura que el requisito no
  pide.

## Pendiente / siguientes pasos

1. **Sin sistema de autenticación de sesión real**: `authorized_order_ids`
   es un campo que el caller debe declarar a mano -- no hay ningún
   mecanismo que derive automáticamente "los pedidos de esta sesión" de
   un JWT/cookie real. Necesario para que el guardrail de autorización
   (caso 3) sea una protección real en producción, no solo una
   demostración del mecanismo.
2. **Heurísticas deterministas, no un clasificador por LLM** -- mismo
   límite que `classify_intent`/`evaluate_for_memory_proposal` desde
   Hito 8 Parte 1: sin credenciales de 4Geeks, cualquier reformulación de
   jailbreak fuera de los patrones probados podría no detectarse. El
   propio `AGENT_SYSTEM_PROMPT` ya le pide al modelo real que rechace
   cambios de instrucciones como defensa de fondo -- los guardrails
   deterministas son la primera línea, no la única.
3. **No se agregó un "comando" alternativo al endpoint de resumen**
   (el checklist acepta "endpoint o comando") -- `GET /agent/guardrails/summary`
   cubre el requisito; `guardrail_audit.read_guardrail_log()` ya permite
   armar un comando/script separado si hiciera falta uno que no dependa
   del servidor corriendo.
