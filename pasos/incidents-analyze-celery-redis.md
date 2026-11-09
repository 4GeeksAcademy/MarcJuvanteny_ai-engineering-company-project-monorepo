# Incidents API — Celery + Redis para la operación pesada de análisis de CSV

Fecha: 2026-09-08

Implementación de la guía "Colas de tareas asíncronas con Celery + Redis":
mover la operación pesada identificada en `services/incidents-api` a un
worker en background, con reintentos, backoff exponencial, Dead Letter
Queue, endpoints de estado/disparo, y monitoreo con Flower.

## Qué operación se movió, y por qué

`Pasos/analisis-endpoints-fastapi-coste-frecuencia.md` (sección 3, tabla de
`/api/incidents`) ya había identificado `POST /api/incidents/analyze` como
**"Muy alto"** coste — el único endpoint con esa calificación en todo el
inventario: *"Lee archivo completo, valida filas y genera resumen agregado;
coste O(n filas)"*. Es la operación pesada de esta entrega.

Antes: el request HTTP bloqueaba hasta terminar `read_csv_text()` (parseo +
validación estructural fila a fila) + `summarize_rows()` (agregación) sobre
el CSV completo, y guardaba el resultado en un global `LAST_ANALYSIS_SUMMARY`
en memoria del proceso de FastAPI.

Ahora: el endpoint solo hace las validaciones baratas y O(1)/O(bytes)
(extensión `.csv`, no vacío, decodificable como UTF-8) y encola una tarea
Celery con el texto del CSV. Todo el trabajo O(n) — `read_csv_text` +
`summarize_rows` — corre en `tasks.py`, en el worker, fuera del ciclo
request/response.

## Dónde vive el código

```
services/incidents-api/
  celery_app.py       # instancia Celery: Redis como broker y result backend
  tasks.py             # analyze_incidents_csv_task (bind=True, max_retries=3, backoff)
                        # + AnalyzeCSVTask.on_failure() -> Dead Letter Queue
  task_dlq.py           # record_dlq_entry(): tabla "task_dlq" en suppliers.json (TinyDB)
  main.py               # POST /api/incidents/analyze (202 + task_id)
                        # GET /tasks/{task_id} (status + result)
                        # GET /api/incidents/results/export?task_id=... (CSV)
  models.py             # + TaskEnqueuedResponse, TaskStatusResponse
  requirements.txt / pyproject.toml  # + celery[redis]
  .env.example           # + REDIS_URL
  README.md              # + cómo levantar/parar el worker, Flower

docker-compose.yml    # + redis, worker, flower
```

## Checklist de la entrega — Infraestructura

- [x] **Redis en `docker-compose.yml`**: imagen oficial `redis:7-alpine`,
  puerto `6379` expuesto, `command: redis-server --maxmemory 256mb
  --maxmemory-policy noeviction`. `noeviction` (no `allkeys-lru` ni similar):
  si se llega al límite de memoria, Redis **rechaza escrituras nuevas** en
  vez de descartar claves existentes en silencio — para un broker de tareas,
  perder un mensaje encolado sin avisar es mucho peor que un error explícito
  que se puede alertar/loguear. Se fijó `maxmemory 256mb` explícito porque
  `noeviction` sin un `maxmemory` configurado es ya el comportamiento por
  defecto de Redis (política *y* límite son necesarios juntos para que la
  política tenga efecto real).
- [x] **Flower en `docker-compose.yml`**: imagen `mher/flower:2.0`, puerto
  `5555`, apuntando al mismo broker (`--broker=redis://redis:6379/0`).
- [x] **API y workers al mismo Redis, URL desde `REDIS_URL`**: `backend` y
  `worker` comparten la misma imagen (`services/Dockerfile`) y el mismo
  `REDIS_URL: redis://redis:6379/0` en `docker-compose.yml`; en local,
  `celery_app.py` lee `REDIS_URL` de `.env` con default
  `redis://localhost:6379/0`.

## Checklist de la entrega — Módulo Celery (`services/`)

- [x] **Instancia Celery con Redis como broker y result backend**:
  `celery_app.py` — `Celery("incidents_api", broker=REDIS_URL, backend=REDIS_URL)`.
- [x] **Al menos una tarea asíncrona (`@app.task`) que encapsula la operación
  pesada**: `tasks.analyze_incidents_csv` (`analyze_incidents_csv_task`,
  `bind=True`) — envuelve `read_csv_text()` + `summarize_rows()`.
- [x] **Reintentos automáticos con `max_retries=3` y backoff exponencial
  (`countdown` creciente entre intentos)**: `countdown = 2 ** (retries + 1)`
  → 2s, 4s, 8s. Solo se reintenta el fallo de `summarize_rows` (cualquier
  `Exception`) — un `CSVInputError` de `read_csv_text` (CSV mal formado) se
  deja fallar **sin reintentar**: es un error determinístico, el mismo CSV
  vuelve a fallar exactamente igual las 3 veces, así que reintentar es puro
  desperdicio de tiempo y de cupo del worker. Ver la sección "Decisiones" más
  abajo.
- [x] **Dead Letter Queue**: cuando una tarea agota `max_retries` (o falla
  sin reintentar, como el `CSVInputError` de arriba), `AnalyzeCSVTask.on_failure()`
  registra en `task_dlq` (tabla nueva en `suppliers.json`, misma base TinyDB
  que `suppliers`/`incidents`/`users`) el `task_id`, número de intento
  (`self.request.retries + 1`), el error (`str(exc)`) y el timestamp
  (`task_dlq.py::record_dlq_entry`).

## Checklist de la entrega — Endpoints de la API

- [x] **El endpoint que antes ejecutaba la operación pesada ahora encola la
  tarea y devuelve `202 Accepted` con `{"task_id": "..."}` de forma
  inmediata**: `POST /api/incidents/analyze` (`main.py`) —
  `analyze_incidents_csv_task.delay(text)`, `response_model=TaskEnqueuedResponse`,
  `status_code=202`.
- [x] **`GET /tasks/{task_id}`**: consulta `AsyncResult(task_id, app=celery_app)`
  en Redis y devuelve `{"task_id": ..., "status": ..., "result": ...}`.
- [x] **`status` refleja los estados reales de Celery**: `pending`, `started`,
  `success`, `failure` — mapeados desde los estados nativos de Celery
  (`PENDING`, `STARTED`, `RETRY` → `started` también, porque para quien
  consulta el estado un reintento en curso sigue "corriendo", `SUCCESS`,
  `FAILURE`). **Nota importante**: `STARTED` solo existe si `task_track_started=True`
  está en la config de Celery (`celery_app.py`) — sin eso, Celery nunca lo
  reporta y salta directo de `PENDING` a `SUCCESS`/`FAILURE`, dejando el
  endpoint sin poder distinguir "en cola" de "corriendo".

## Checklist de la entrega — Worker

- [x] **Corre como proceso independiente, no dentro de FastAPI**:
  `docker-compose.yml` define `worker` como servicio separado de `backend`
  (misma imagen, comando distinto: `celery -A celery_app worker --loglevel=info`
  en vez de `uvicorn`). `main.py` nunca ejecuta `tasks.py` en el hilo de un
  request — solo `.delay()` (encolar) y `AsyncResult` (consultar), ambos
  operaciones de Redis, no de CPU/IO pesado.
- [x] **Documentado en el README**: `services/incidents-api/README.md` →
  sección "Background worker (Celery + Redis)" — cómo levantarlo (`docker
  compose up ... worker`, o `celery -A celery_app worker --loglevel=info`
  local) y cómo detenerlo (`docker compose stop worker` / `Ctrl+C`), más
  cómo acceder a Flower.

## Checklist de la entrega — Observabilidad

- [x] **Cada tarea registra en el log `task_id`, intento, estado resultante y
  duración**: esto ya lo hace Celery de fábrica en el log del worker (nivel
  `INFO`) — `Task tasks.analyze_incidents_csv[<task_id>] received` /
  `succeeded in <duración>s: <resultado>` / `raised unexpected: <error>` (ver
  ejemplos reales en "Cómo se verificó"). No se agregó logging propio encima
  porque hubiera sido puramente redundante con lo que Celery ya expone; el
  intento (`self.request.retries`) sí es explícito en la traza de Celery
  ("Retry" vs "raised unexpected") y además queda persistido en la DLQ para
  cualquier fallo definitivo.
- [x] **Los fallos registran adicionalmente el mensaje de error completo**:
  la traceback completa va al log del worker (comportamiento estándar de
  Celery), y el mensaje de error (`str(exc)`) queda además persistido en
  `task_dlq` para cualquier fallo definitivo — no solo en el log efímero del
  proceso.
- [x] **Flower accesible y muestra las tareas encoladas, en proceso y
  completadas**: verificado con un contenedor real de `mher/flower:2.0` +
  un worker real de este servicio, ambos contra el mismo Redis (ver "Cómo se
  verificó"). En el camino se encontró y corrigió un bug real de sintaxis:
  `command: celery flower --broker=... --port=5555` (orden original) hace
  que la imagen **ignore `--broker` en silencio** (log: *"You have
  incorrectly specified the following celery arguments after flower
  command"*) y Flower cae al broker por defecto
  (`amqp://guest@localhost:5672//`, RabbitMQ) — o sea, se conecta a un
  broker que ni siquiera existe en este stack, en vez de al Redis real. El
  flag va **antes** del subcomando `flower` (es un flag de `celery`, no de
  `flower`): `celery --broker=redis://redis:6379/0 flower --port=5555` — así
  quedó en `docker-compose.yml`, con un comentario explicando por qué.

## Cómo se verificó

Se levantaron contenedores Docker reales de Redis y Postgres (no SQLite/mocks
esta vez, a diferencia de las entregas anteriores — aquí sí había Docker
disponible en el entorno) y se corrió la app y el worker reales:

1. `docker run redis:7-alpine --maxmemory 256mb --maxmemory-policy noeviction`
   y `docker run postgres:16-alpine`.
2. `celery -A celery_app worker --loglevel=info` (worker real, no eager) +
   `uvicorn main:app` (API real) contra esos contenedores.
3. Creado un usuario de prueba, logueado, y ejercitado el flujo completo por
   HTTP con `curl`:
   - `POST /api/incidents/analyze` con un CSV válido → `202` +
     `{"task_id": "..."}` inmediato.
   - `GET /tasks/{task_id}` → `{"status": "success", "result": {...}}` con
     el resumen agregado correcto.
   - `GET /api/incidents/results/export?task_id=...` → CSV de resultados
     correcto.
   - Log real del worker: `Task tasks.analyze_incidents_csv[...] received`
     → `succeeded in 0.0096s: {...}`.
4. CSV mal formado (columnas faltantes) → `POST /api/incidents/analyze` →
   `202` igual (el error estructural ya no se descubre en el request, ver
   "Decisiones" abajo) → `GET /tasks/{task_id}` → `{"status": "failure"}` →
   log del worker confirma **un solo intento, sin reintentos** (`CSVInputError`
   no es retryable) → `task_dlq` en `suppliers.json` queda con
   `{"task_id": ..., "attempt": 1, "error": "CSV format is invalid: missing
   required columns: ...", "timestamp": ...}`.
5. Backoff + DLQ tras agotar reintentos, con un script de verificación
   aparte (`.apply()` en modo eager local, monkeypatcheando `summarize_rows`
   para simular fallos transitorios — así se puede interceptar la llamada
   sin depender de temporización real de un worker separado):
   - `summarize_rows` falla 2 veces y tiene éxito la 3ª → la tarea termina en
     `SUCCESS` tras 2 reintentos, **sin** entrada en la DLQ.
   - `summarize_rows` falla siempre → 1 intento inicial + 3 reintentos = 4
     llamadas totales, la tarea termina en `FAILURE`, y queda **una** entrada
     en la DLQ con `attempt: 4` y el mensaje del último error.
6. Flower real: contenedor `mher/flower:2.0` en su propia red Docker,
   apuntado (con la sintaxis corregida, ver arriba) al mismo Redis que un
   worker real de este servicio. `GET /api/workers` de Flower devolvió el
   worker conectado (`celery@...`) con `tasks.analyze_incidents_csv` en su
   lista de tareas registradas; tras `analyze_incidents_csv_task.delay(...)`,
   `GET /api/tasks` mostró esa tarea con `state: "SUCCESS"`, `worker`,
   `args`, `result` y `runtime` correctos.

Todos los contenedores, la red Docker y los archivos de prueba (usuario de
prueba insertado en `suppliers.json`, `.env` local) se descartaron/revirtieron
al terminar — `suppliers.json` quedó exactamente como estaba antes de esta
verificación (`git diff` vacío) y no quedó ningún contenedor/red huérfano
(`docker ps -a` vacío al cierre).

## Decisiones de implementación no cubiertas por la guía genérica

- **Qué error es "retryable"**: la guía pide `max_retries=3` + backoff sin
  distinguir tipos de error. Se decidió **no** reintentar `CSVInputError`
  (CSV estructuralmente inválido) porque es un fallo determinístico del
  input, no transitorio — reintentar 3 veces el mismo CSV mal formado solo
  quema tiempo de worker y demora inútilmente que el resultado llegue a
  `failure`. Sí se reintenta cualquier otra excepción de `summarize_rows`
  (agregación pura sobre filas ya validadas), donde un fallo inesperado es
  más plausible que sea transitorio (memoria, etc.).
- **`GET /api/incidents/results/export` ahora requiere `task_id`**: antes
  dependía de un global `LAST_ANALYSIS_SUMMARY` en memoria del proceso de
  FastAPI. Con el worker corriendo en un **proceso separado**, ese global ya
  no puede funcionar — el worker nunca comparte memoria con la API. Se
  cambió el contrato del endpoint a `?task_id=...`, leyendo el resultado
  directo del result backend de Celery (Redis) vía `AsyncResult`. Esto
  además es más correcto: con tareas concurrentes, "el último análisis" ya
  no es un concepto bien definido si dos usuarios suben CSVs al mismo tiempo.
  No estaba en el checklist de la guía, pero dejar el endpoint roto (el
  global nunca se vuelve a poblar) hubiera sido peor que adaptarlo.
- **Deteccion de errores CSV pasó de síncrona a asíncrona**: antes,
  `POST /api/incidents/analyze` devolvía `422`/`415` inmediato si el CSV
  tenía columnas faltantes o filas malformadas (`read_csv_text` corría en el
  request). Ahora esa validación es parte del trabajo O(n) que se movió al
  worker, así que un CSV mal formado ya no se rechaza en el request — se
  descubre vía `GET /tasks/{task_id}` → `status: "failure"`. Es la
  consecuencia directa (y correcta) de mover **todo** el trabajo O(n), no
  solo la agregación, al worker — es justo la parte que hacía "Muy alto" el
  coste del endpoint original.
- **DLQ en TinyDB (`suppliers.json`), no en una tabla nueva de Postgres**:
  mismo criterio que el resto de tablas de este servicio
  (`suppliers`/`incidents`/`users`) — bookkeeping ligero, propio de
  `incidents-api`, sin necesidad de una migración SQL nueva.

## Pendiente / siguientes pasos

1. No hay endpoint para **listar** la DLQ (`task_dlq`) — hoy solo se puede
   inspeccionar leyendo `suppliers.json` directo. No pedido por esta guía;
   si hace falta un panel de fallos, sería un endpoint de solo lectura nuevo
   sobre `task_dlq.py`.
2. `GET /tasks/{task_id}` con un `task_id` que nunca existió devuelve
   `{"status": "pending"}` en vez de `404` — es el comportamiento nativo de
   Celery/Redis (`AsyncResult` no puede distinguir "nunca existió" de "está
   en cola, todavía no lo tomó ningún worker"). Documentado aquí como
   limitación conocida, no como bug: no hay forma barata de diferenciar esos
   dos casos sin persistir aparte qué `task_id` se emitieron de verdad.
