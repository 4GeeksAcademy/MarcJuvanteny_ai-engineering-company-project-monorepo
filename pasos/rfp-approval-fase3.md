# Aprobación humana por departamento y cierre del documento — Hito 9 · Parte 3

Fecha: 2026-10-26

Implementación de `CONTEXT/CONTEXT9.md` (Hito 9, Parte 3): el responsable
nombrado de cada departamento activo (§2.1) aprueba su sección de forma
independiente, sin bloquear a los demás, usando un punto de interrupción
real de LangGraph (`interrupt`/`Command(resume=...)`) con checkpointer
persistente en Postgres; un nodo de arbitraje determinista (§7, "Triggers
de conflicto y árbitro fijo") resuelve contradicciones cruzadas entre
secciones; y el documento final se genera solo cuando todos los
departamentos activos aprueban.

El checklist se compartió en dos imágenes: la primera con "Aprobación
humana por departamento", "Guardrails y control de flujo", "Identidad del
checkpointer", "Cierre del documento" y el inicio de "Revisión de extremo
a extremo"; la segunda repitió el final de "Cierre del documento" +
completó "Revisión de extremo a extremo" + mostró el título "Pruebas" sin
bullets visibles (cortada igual que pasó con otras secciones en rondas
anteriores de este mismo Hito) -- implementado todo lo visible; "Pruebas"
se cubre igual con la suite real que ya existía más la nueva de esta
entrega (ver "Cómo se verificó"), sin adivinar un requisito adicional no
visible.

## Dónde vive el código

```
data/pipelines/rfp_intake/
  arbitration.py            # NUEVO -- los 3 triggers de CONTEXT9.md §7, deterministas
  approval_graph.py          # NUEVO -- grafo interrupt/resume + arbitraje + cierre
  models.py                   # EXTENDIDO -- FinalDocument, RFPNodeTrace
  pipeline.py                  # EXTENDIDO -- start_or_get_approval_round, resume_department_approval

services/incidents-api/
  routers/rfp.py                # EXTENDIDO -- POST /approval/start, POST /approval/{department_id}
  pyproject.toml                 # EXTENDIDO -- langgraph-checkpoint-postgres (mismo motivo que langgraph/markitdown)

uis/backoffice/src/components/
  rfp-intake-panel.tsx            # EXTENDIDO -- disparar generación (Parte 2) + aprobar/rechazar por departamento + ver documento final

scripts/rfp_reprocess.py          # EXTENDIDO -- `--e2e-smoke`: Parte 1 -> 2 -> 3 completa, con aprobaciones simuladas

tests/pipelines/
  test_rfp_arbitration.py          # NUEVO
  test_rfp_approval_graph.py        # NUEVO
```

## Cómo correrlo

```bash
# Backend (API + Celery + Postgres + Redis ya deben estar arriba, igual que Partes 1-2)
cd services/incidents-api
uvicorn main:app --reload
celery -A celery_app worker --loglevel=info   # otra terminal

# Arrancar (o releer, si ya está en curso) la ronda de aprobación de un ticket
# que ya salió de la Parte 2 (en_evaluación o needs_human_review)
curl -X POST http://localhost:8000/rfp/tickets/<id>/approval/start -H "Authorization: Bearer <token>"

# Resolver la aprobación de UN departamento (resume explícito)
curl -X POST http://localhost:8000/rfp/tickets/<id>/approval/warehouse \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"decision": "approve"}'
#  o: {"decision": "reject", "reason": "..."} / {"decision": "request_changes", "reason": "..."}

# Ver el ticket completo (secciones + documento final si ya cerró)
curl http://localhost:8000/rfp/tickets/<id> -H "Authorization: Bearer <token>"
```

```bash
# Ruta E2E reproducible (checklist "Revisión de extremo a extremo", item 2) --
# sube trackflow-request-1.pdf y corre las 3 Partes completas, con
# aprobaciones SIMULADAS (resume programático, nunca un click de UI)
cd data/pipelines
.venv/bin/python ../../scripts/rfp_reprocess.py --e2e-smoke
```

```bash
# Tests (sin Postgres/Celery, deterministas -- MemorySaver en vez de PostgresSaver)
cd data/pipelines
.venv/bin/python -m pytest ../../tests/pipelines/test_rfp_arbitration.py \
  ../../tests/pipelines/test_rfp_approval_graph.py -v
```

## Checklist de la entrega

### Aprobación humana por departamento

- [x] **Punto de interrupción (`interrupt`) antes de dar por aprobada una
  sección**: cada nodo `{dept}_approval` (`approval_graph.py`) llama
  `interrupt(...)` con el borrador + su evaluación de la Parte 2 -- la
  decisión humana nunca se asume, se espera de verdad.
- [x] **La interrupción pausa ÚNICAMENTE la rama de ese departamento**:
  verificado empíricamente ANTES de construir el grafo real (ver "Cómo se
  verificó") -- `interrupt()` genera un `id` propio por nodo dentro del
  mismo `thread_id`; resolver uno con `Command(resume={ese_id: valor})`
  avanza solo esa rama, la otra queda intacta y resumible.
- [x] **Checkpointer antes de cada interrupción, ejecución reanudable**:
  `PostgresSaver` real (`langgraph-checkpoint-postgres`) -- cada
  interrupción ya queda persistida en Postgres por diseño de LangGraph;
  verificado reanudando desde una conexión de Postgres COMPLETAMENTE
  NUEVA (simulando otro proceso) antes de confiar en el patrón.
- [x] **`resume` como punto de entrada explícito, no un reinicio
  completo**: `pipeline.py::resume_department_approval()` nunca
  reconstruye el estado inicial -- localiza el `interrupt` pendiente de
  ESE departamento (`compiled.get_state(config)`) y lo reanuda con
  `Command(resume=...)`.
- [x] **Valida la respuesta humana antes de dejarla entrar al grafo**:
  `ApprovalDecision` (Pydantic, `decision: Literal["approve", "reject",
  "request_changes"]`) se valida ANTES de construir el `Command` -- tanto
  en `pipeline.py` como de nuevo en FastAPI (`routers/rfp.py` usa el
  MISMO modelo como body del endpoint, nunca un schema duplicado).
- [x] **Extiende la interfaz de ticket de la Parte 1**:
  `rfp-intake-panel.tsx` -- cada departamento pendiente se muestra con su
  borrador, su responsable fijo, un campo de motivo, y 3 botones
  (Aprobar / Pedir cambios / Rechazar).

### Guardrails y control de flujo

- [x] **Límite máximo de iteraciones en cualquier ciclo restante entre
  departamentos**: `MAX_APPROVAL_ITERATIONS = 3` (rechazo/cambios
  solicitados por el propio aprobador) y `MAX_ARBITRATION_ROUNDS = 2`
  (reescrituras forzadas por arbitraje) -- dos ciclos distintos, dos
  límites distintos, ninguno indefinido.
- [x] **Nodo de arbitraje explícito, disparado por contradicciones en
  estado estructurado, resuelto por el árbitro fijo** (`arbitration.py`,
  `CONTEXT9.md` §7 EXACTA -- nunca un LLM "negociando" entre agentes):
  - `volume-vs-capacity`: capacidad de warehouse vs. volumen asumido por
    lastmile -- árbitro Miguel Torres, limita el volumen a la capacidad
    (ver "Decisiones" sobre `WAREHOUSE_MAX_MONTHLY_CAPACITY`).
  - `returns-sla-breach`: cualquier sección promete devoluciones <48h --
    Sofía Ramos si es solo `reverse`, Miguel Torres si otro departamento
    también lo promete.
  - `currency-mismatch`: una sección cotiza en una moneda distinta a la
    esperada según `client_country` -- Miguel Torres, reescribe a la
    moneda correcta.
- [x] **Trazabilidad por ejecución de nodo** (agente, input, output,
  timestamp): `RFPNodeTrace` (Postgres, nueva tabla) -- cada nodo del
  grafo de aprobación llama a `trace_fn` (inyectable), persistida
  independientemente del estado efímero de LangGraph.

### Identidad del checkpointer

- [x] **`thread_id` namespaced por `ticket_id`**: `rfp-{ticket_id}` -- un
  solo hilo por ticket (no uno por departamento, ver "Decisiones" sobre
  por qué un solo hilo ya aísla las ramas correctamente); tickets
  concurrentes nunca comparten checkpoint.

### Cierre del documento

- [x] **Documento final solo cuando TODOS los departamentos activos
  aprueban**: `close_document` (`approval_graph.py`) chequea
  `all(decisions[d].status == "approved" for d in departments_needed)` --
  si falta uno, `final_document` queda `None` y el grafo no avanza a
  `terminado`.
- [x] **`esperando_aprobación` mientras algo esté pendiente;
  `terminado` + documento accesible cuando cierra**:
  `pipeline.py::resume_department_approval()` -- `FinalDocument`
  persistido en Postgres (`ticket_id`, `sections`, `currency`,
  `generated_at`), `get_ticket_with_metadata()` lo incluye en `GET
  /rfp/tickets/{id}` (nunca un dato que solo vive en la respuesta de un
  solo request).

### Revisión de extremo a extremo

- [x] **Al menos 1 RFP de prueba corrida por las 3 Partes completas**:
  `scripts/rfp_reprocess.py --e2e-smoke` -- ver "Cómo se verificó".
- [x] **Ruta E2E reproducible (fixture + script), aprobaciones
  simuladas, no dependiente de clicks de UI**: el mismo script, con
  `resume_department_approval(..., {"decision": "approve"})`
  programático -- cero interacción humana/UI.
- [x] **Corrige cualquier salto/inconsistencia encontrada en la
  transición entre partes**: 2 bugs reales encontrados y corregidos esta
  ronda (ver "Cómo se verificó" #1 y #2) -- ninguno hipotético.

## Cómo se verificó

Sin credenciales de 4Geeks para arbitraje/aprobación por LLM (mismo
límite de toda la sesión -- de hecho acá es LITERALMENTE lo que pide
CONTEXT9.md §7: "árbitro fijo, no un LLM"), pero con LangGraph real,
Postgres real (`PostgresSaver`, no simulado), HTTP real, Celery real, y
los tickets reales ya persistidos por las Partes 1-2 (nunca datos de
prueba inventados para esta verificación):

1. **Bug real de diseño encontrado y corregido ANTES de aceptar la
   arquitectura -- condición de carrera entre el self-loop de un
   departamento y el join de `arbitrate`**: el primer diseño dejaba que
   cada `{dept}_approval` decidiera por sí mismo "me auto-enlazo" (si
   necesita otra ronda) vs. "voy a `arbitrate`" (si ya se asentó).
   Reproducido corriendo el grafo antes de construir todo lo demás sobre
   él: si warehouse se aprueba y lastmile necesita otra ronda en el MISMO
   superstep, `arbitrate` corre con SOLO warehouse como predecesor activo
   (lastmile se auto-enlazó, no apunta a `arbitrate` ese superstep) y, al
   decidir su siguiente paso, también intenta enrutar de vuelta a
   `lastmile_approval` -- dos caminos agendando el mismo nodo en el mismo
   superstep, duplicando la interrupción de lastmile (confirmado: el
   segundo `Command(resume=...)` devolvía OTRA interrupción para
   lastmile en vez de cerrar). Corregido eliminando el self-loop por
   completo: TODO resultado de `{dept}_approval` toma la MISMA arista
   estática hacia `arbitrate` (igual que `graph.py` Parte 1,
   `*_worker -> synthesize`) -- un join real que sí espera a todos los
   departamentos activos de la ronda porque ninguno se desvía por su
   cuenta.
2. **Bug real encontrado y corregido -- `volume-vs-capacity` no
   cambiaba ningún número real**: el mecanismo genérico de feedback de
   la Parte 2 (`generators.py::_apply_feedback`, reutilizado acá para que
   el generador reaccione al `rule_applied` del árbitro) solo sabe
   reaccionar a TOKENS de texto (`currency_match`, `sla_stated`, etc.) --
   para `currency-mismatch`/`returns-sla-breach` esto alcanza (verificado:
   una sección con moneda incorrecta se reescribe limpia). Para
   `volume-vs-capacity` la regla exige CAMBIAR un número
   (`monthly_volume`), no agregar una aclaración de texto -- sin esto, el
   borrador regenerado repetía el mismo volumen y el trigger volvía a
   dispararse indefinidamente. Encontrado corriendo este caso REAL contra
   el ticket 2 (Luna Cosmetics, `monthly_volume=5000`, por encima de
   `WAREHOUSE_MAX_MONTHLY_CAPACITY=4000`) -- corregido con
   `_apply_arbitration_fix()`: para ese trigger específico, `arbitrate`
   cambia `key_aspects["monthly_volume"]` al tope ANTES de regenerar, y
   el nuevo valor se persiste en la sección (no solo en el borrador de
   texto).
3. **Aislamiento de ramas por interrupción, verificado ANTES de construir
   el grafo real**: un grafo mínimo de prueba con 2 nodos en paralelo
   llamando `interrupt()` -- resolver uno con
   `Command(resume={ese_id: valor})` avanzó SOLO esa rama, la otra quedó
   con su `Interrupt` intacto y resumible después. Confirmado también
   que un nodo puede auto-enlazarse (rechazo -> regenera -> vuelve a
   interrumpir) sin perder el aislamiento de la otra rama.
4. **Reanudación verdaderamente cross-process, con `PostgresSaver` real**:
   un hilo iniciado con una conexión de Postgres, cerrada por completo
   (`conn.close()`), se reanudó exitosamente desde una conexión
   COMPLETAMENTE NUEVA (`get_state()` encontró el `Interrupt` pendiente,
   `Command(resume=...)` lo resolvió) -- confirma que la persistencia es
   real, no solo en memoria del proceso que arrancó el grafo.
5. **`tests/pipelines/test_rfp_arbitration.py` (10 tests) +
   `test_rfp_approval_graph.py` (9 tests), 19/19 en verde**, corridos
   junto con los 42 tests de Partes 1-2 -- 61/61 sin regresiones.
   `test_rfp_approval_graph.py` prueba explícitamente: aislamiento de
   ramas, rechazo-regenera-reinterrumpe, agotamiento de iteraciones →
   `rejected_final` (nunca se descarta la sección), documento final solo
   si TODOS aprueban, y arbitraje reabriendo un departamento YA aprobado
   por un humano que no notó un error real.
6. **Flujo de Postgres real, llamando directamente
   `pipeline.py`**: `start_or_get_approval_round`/`resume_department_approval`
   contra los tickets 1 (ModaViva) y 2 (Luna Cosmetics) -- ticket 1 cerró
   limpio en `terminado` con `FinalDocument` real en la primera ronda;
   ticket 2 disparó `volume-vs-capacity` DE VERDAD (su `monthly_volume`
   real de la Parte 1 es 5000, por encima del tope) -- 2 rondas de
   aprobación, la segunda con el volumen corregido a 4000, cerró limpio.
   Confirmado también: releer la ronda (`start_or_get_approval_round`)
   sin resolver nada es idempotente (no reinvoca el grafo).
7. **Flujo HTTP + Celery real, extremo a extremo, con un ticket subido
   por el endpoint real** (no datos sembrados a mano): `uvicorn` real +
   worker de Celery real + usuario autenticado real + `POST
   /rfp/tickets` con `trackflow-request-2.pdf` real (ticket 10, nuevo) →
   Parte 1 (`analisis_completo`) → `POST .../generate` (Parte 2,
   `en_evaluación`) → `POST .../approval/start` (Parte 3,
   `esperando_aprobación`) → arbitraje real por `volume-vs-capacity`
   (mismo caso que Luna Cosmetics) → segunda ronda → `POST
   .../approval/{dept}` × 2 → `terminado` con `FinalDocument` real,
   confirmado con `GET /rfp/tickets/10`.
8. **Ruta E2E reproducible corrida de verdad**:
   `scripts/rfp_reprocess.py --e2e-smoke` -- sube
   `trackflow-request-1.pdf` como ticket nuevo (11), corre las 3 Partes
   con `process_rfp_ticket` → `process_rfp_generation` →
   `start_or_get_approval_round` → `resume_department_approval(...,
   {"decision": "approve"})` × N departamentos, con ASERCIONES reales en
   cada transición (`departments_needed` consistente entre Partes 1-2-3,
   ningún departamento perdido, `FinalDocument` no-nulo, cada sección
   `approval_status == "approved"` al cerrar) -- terminó en `terminado`
   limpio, `exit code 0`, sin arbitraje esta vez (ModaViva: volumen 3200,
   bajo el tope).
9. **La UI (`rfp-intake-panel.tsx`) se extendió y tipó (build + type-check
   de Next.js en verde) y se confirmó que la ruta `/rfp` sirve `200` con
   `next dev` real** -- pero, igual que en la Parte 1, NO se recorrió
   clic-por-clic en un navegador real esta ronda (sin herramienta de
   browser automation disponible en esta sesión) -- decirlo
   explícitamente en vez de afirmar un resultado no comprobado. Los
   endpoints que esa UI llama (`/approval/start`, `/approval/{dept}`) ya
   están verificados por HTTP real en el punto 7, con el mismo contrato
   de payload/respuesta.
10. **Limpieza tras la verificación**: `.env` temporal de
    `services/incidents-api` eliminado, usuario de prueba revertido de
    `suppliers.json` (`git checkout --`), procesos de
    `uvicorn`/`celery`/`next dev` terminados, PDFs de prueba subidos bajo
    `data/raw/` eliminados (nunca se commitean -- son artefactos runtime
    de la recepción, `CONTEXT9.md` §2.4), y las filas de
    `RFPNodeTrace`/`checkpoints` generadas por experimentos EXPLORATORIOS
    de diseño (antes de aceptar la arquitectura final del grafo, con
    `ticket_id` reutilizado como dato de prueba) se identificaron por
    timestamp y se borraron -- los tickets 1, 2, 10 y 11 quedan en
    `terminado` con su `FinalDocument` real y su traza real intacta,
    como evidencia genuina de la verificación (misma lógica que Partes
    1-2: son fixtures de smoke-test, no datos de producción).

## Decisiones de implementación no cubiertas por la guía genérica

- **Un solo `thread_id` por ticket (`rfp-{ticket_id}`), no uno por
  departamento**: el checklist ofrecía ambas opciones ("o
  `rfp-{ticket_id}:{department}`"). Un solo hilo ya aísla las ramas
  correctamente (verificado antes de decidir, ver "Cómo se verificó" #3)
  -- un hilo por departamento habría sido una capa de indirección extra
  sin ganancia real, y habría complicado el join real hacia `arbitrate`
  (que necesita ver el estado de TODOS los departamentos a la vez para
  detectar conflictos cruzados).
- **`arbitrate` como join ESTÁTICO único, nunca un self-loop por
  departamento**: ver bug #1 de "Cómo se verificó" -- la causa raíz real
  de la condición de carrera encontrada, no una elección de estilo.
- **`WAREHOUSE_MAX_MONTHLY_CAPACITY = 4000` (constante operativa de
  TrackFlow, documentada en `arbitration.py`)**: `CONTEXT9.md` §7 define
  el trigger `volume-vs-capacity` pero nunca da un número -- la RFP solo
  trae el volumen que el CLIENTE pide, nunca la capacidad propia de
  TrackFlow (sería inventar un dato del cliente). Se documenta
  explícitamente como una constante de negocio asumida, no derivada de
  ningún documento -- y sirvió para encontrar un bug real (#2) al
  probarla contra datos reales de la Parte 1 (Luna Cosmetics,
  `monthly_volume=5000`).
- **`approval_status`/`approver`/`approved_at` de `RFPDepartmentSection`
  se reutilizan para la decisión de la Parte 3** (`"approved"` /
  `"rejected_final"` / `"pending"`), sobrescribiendo el
  `"needs_human_review"` que pudo haber dejado la Parte 2 -- esos 3
  campos ya existían desde la Parte 1 explícitamente predeclarados para
  este uso ("para que Partes 2 y 3 no necesiten una migración nueva").
- **Un ticket con una sección `rejected_final` se queda en
  `esperando_aprobación` para siempre** (nunca pasa a `terminado`, nunca
  se inventa un estado nuevo tipo "rechazado"): `CONTEXT9.md` no define
  un estado terminal para "nunca se aprobó" -- generar un documento
  final incompleto sería peor que dejarlo visible y pendiente para que un
  humano decida el siguiente paso fuera del grafo (reprocesar, cancelar
  el ticket a mano, etc. -- fuera del alcance de esta entrega).
- **Nuevos endpoints síncronos (`POST .../approval/start`,
  `POST .../approval/{dept}`), sin Celery** -- a diferencia de Partes 1-2
  (conversión de PDF, LLM), una decisión de aprobación es una transición
  de estado de grafo determinista y rápida (sin I/O lento) -- encolarla
  en Celery habría sido indirección sin beneficio real, y habría hecho
  más difícil devolver el resultado (`pending_approvals`/`final_document`)
  de inmediato a quien llama.
- **`FinalDocument.sections` es un snapshot (texto plano), no una
  referencia viva a `RFPDepartmentSection`**: el documento final no debe
  cambiar si alguien edita una sección después del cierre -- aunque hoy
  no hay un flujo de edición post-cierre, modelarlo como snapshot desde
  el día uno evita una futura migración de datos si ese flujo se agrega.

## Pendiente

- **UI no verificada clic-por-clic en un navegador real** -- ver "Cómo se
  verificó" #9: build + type-check + `next dev` real sirviendo `200` sí
  se hicieron, pero no una sesión interactiva real (sin herramienta de
  browser automation disponible en esta sesión).
- **Sección "Pruebas" del checklist, sin bullets visibles en ninguna de
  las 2 imágenes compartidas** -- cubierta con la suite real existente
  (61 tests, ver "Cómo se verificó" #5) más la ruta E2E reproducible,
  pero sin ver el bullet exacto no se sabe si pedía algo adicional
  específico no cubierto.
- **Edición/regeneración manual de una sección ya `terminado`**: fuera de
  alcance de `CONTEXT9.md` (no lo pide ninguna de las 3 Partes) -- una
  vez el documento final se genera, esta entrega no ofrece un flujo para
  revisarlo o corregirlo.
