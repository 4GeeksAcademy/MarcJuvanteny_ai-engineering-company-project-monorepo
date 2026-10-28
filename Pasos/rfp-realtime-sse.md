# Notificación en tiempo real de tickets de RFP (SSE) — Hito 10 · Parte 1

Fecha: 2026-10-28

Implementación de `CONTEXT/CONTEXT10.md` ("BRIEFING — TrackFlow: Sistemas
en Tiempo Real", Parte 1): el equipo de **Miguel Torres** (Commercial
Director) ya no tiene que revisar el dashboard por su cuenta para enterarse
de que llegó una RFP. Cada ticket que el clasificador acepta como RFP válida
(`status = analizando`) se empuja por un stream **SSE** autenticado al panel
"Recepción de RFPs" del backoffice, que lo muestra al instante, resaltado,
sin recargar la página.

No se rediseña el sistema multiagente de Hito 9: solo se le agrega la
notificación. Se reutilizan exactamente las entidades y los nombres de
campo que ya existían (`RFPTicket`, `RFPMetadataRecord`), tal como pide
CONTEXT10.md §5.

## Dónde vive el código

```
data/pipelines/rfp_intake/
  events.py                    # NUEVO -- outbox RFPTicketEvent (tabla rfp_ticket_events) + payload rfp_ticket_created
  models.py                     # EXTENDIDO -- create_tables() también crea rfp_ticket_events
  pipeline.py                    # EXTENDIDO -- graph.stream(): anuncia el ticket al salir de `classify`

services/incidents-api/
  routers/rfp_events.py          # NUEVO -- GET /rfp/events (SSE, mismo JWT, keep-alive, Last-Event-ID)
  main.py                         # EXTENDIDO -- app.include_router(rfp_events_router)
  pyproject.toml / uv.lock        # EXTENDIDO -- dependency-group `dev` con pytest (tests/services/)

uis/backoffice/src/
  lib/use-rfp-ticket-stream.ts    # NUEVO -- fetch + ReadableStream, parser SSE, backoff, watchdog, Last-Event-ID
  components/rfp-intake-panel.tsx # EXTENDIDO -- consume el stream, dedupe por ticket_id, aviso + resaltado "Nueva"
  app/globals.css                  # EXTENDIDO -- .rfp-live-pill, .rfp-arrival-banner, .rfp-ticket-new, .rfp-new-badge

tests/
  services/test_rfp_events_stream.py        # NUEVO -- endpoint SSE por HTTP real + caída/reconexión/replay
  pipelines/test_rfp_ticket_created_event.py # NUEVO -- el evento sale tras `classify`, antes de los workers
```

## Contrato del stream

`GET /rfp/events` — `Authorization: Bearer <JWT del backoffice>`, opcional
`Last-Event-ID: <n>`.

```text
retry: 2000
id: 41
: connected

id: 42
event: rfp_ticket_created
data: {"ticket_id":17,"rfp_id":9,"client_name":"Northline Apparel","client_country":"USA","services_requested":["warehouse","lastmile"],"status":"analizando","created_at":"2026-07-24T14:32:00Z"}

: keep-alive

```

- **Evento con nombre** `rfp_ticket_created`, nunca el genérico `message`.
- **`data:`** es solo el JSON del ticket (sin sobre `{"event","data"}`), con
  los campos de CONTEXT10.md §3: `ticket_id`, `rfp_id`, `client_name`,
  `client_country`, `services_requested`, `status`, `created_at`.
- **`id:`** es el id del outbox (`rfp_ticket_events.id`), monotónico.
- **Frame de apertura**: `retry:` (primer reintento sugerido) + `id:` con el
  cursor actual, **sin `data:`** — no dispara evento, pero le da al cliente
  un `Last-Event-ID` válido aunque se caiga antes de recibir el primero.
- **Keep-alive**: comentario `: keep-alive` cada 15 s sin eventos.
- **Headers**: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
  `Connection: keep-alive`, `X-Accel-Buffering: no` (sin buffering en nginx).
- **Auth**: el mismo `auth_service.get_user_from_token` que el resto de
  `/rfp/*`. Sin token, o con un token inválido → `401` y nunca se abre el
  stream.

## Cómo correrlo

```bash
# Backend (igual que Hito 9: API + worker de Celery + Postgres + Redis)
cd services/incidents-api
uvicorn main:app --reload --port 8001
celery -A celery_app worker --loglevel=info      # otra terminal

# Backoffice
cd uis/backoffice && npm run dev                  # http://localhost:3000/rfp

# Ver el wire crudo (-N: sin buffer en curl)
curl -N http://localhost:8001/rfp/events -H "Authorization: Bearer <token>"
curl -N http://localhost:8001/rfp/events -H "Authorization: Bearer <token>" -H "Last-Event-ID: 0"  # replay completo
```

La tabla `rfp_ticket_events` la crea sola el startup de la API
(`create_rfp_tables()`), igual que el resto de tablas de `rfp_intake`.

```bash
# Tests del endpoint SSE (venv del servicio: importan auth_service/routers reales)
cd services/incidents-api
uv run --group dev pytest ../../tests/services -q

# Test del momento de emisión (venv de data/pipelines, como el resto de tests RFP)
cd data/pipelines
.venv/bin/python -m pytest ../../tests/pipelines/test_rfp_*.py -q
```

## Decisiones

**Outbox en Postgres, no pub/sub en memoria.** El ticket se clasifica en el
worker de Celery (otro proceso); un `asyncio.Queue` dentro de FastAPI nunca
lo vería. El pipeline escribe el evento en `rfp_ticket_events` **en la
misma transacción** que el `RFPMetadataRecord` (nunca un evento sin
metadata, ni al revés), y el endpoint SSE lee la tabla cada 1 s por cliente
conectado. Para el volumen de un backoffice comercial (pocas pestañas
abiertas, unas cuantas RFP al día) un `SELECT ... WHERE id > n` indexado por
segundo no supone carga; si algún día hiciera falta, `LISTEN/NOTIFY` de
Postgres puede despertar el loop sin cambiar el contrato del wire. No hace
falta infraestructura nueva (ni Redis pub/sub, ni un broker extra).

**Momento exacto de emisión.** `process_rfp_ticket` pasó de
`graph.invoke()` a `graph.stream(stream_mode="values")`: en cuanto el nodo
`classify` devuelve `is_valid = True` (ya trae la metadata extraída), se
persisten metadata + evento y se hace commit, con el ticket todavía en
`analizando`. Workers y synthesizer siguen corriendo después; Ventas ve la
RFP antes de que termine el análisis. Un documento descartado nunca emite
evento. `record_ticket_created` es idempotente por `ticket_id`: reprocesar
un ticket (`scripts/rfp_reprocess.py --ticket-id`) no emite un segundo
evento.

**Valores del dominio: los del sistema real.** CONTEXT10.md §5 dice
"los nombres de campos deben coincidir exactamente con los que ya usaste en
el sistema de RFPs". El ejemplo de §3 usa `"analyzing"` / `"US"`, pero este
sistema persiste los valores de CONTEXT9.md §2.3: `status = "analizando"` y
`client_country ∈ {"USA", "Spain"}`. El evento usa esos valores reales: si
el stream dijera `"analyzing"` y `GET /rfp/tickets` dijera `"analizando"`,
la UI tendría dos estados distintos para el mismo ticket.

**`rfp_id`** = id del `RFPMetadataRecord` del ticket (la entidad "RFP"
1:1 con el ticket en este sistema; `RFPTicket` no tiene una columna
`rfp_id` propia). `ticket_id` y `rfp_id` son enteros, como en el resto de
la API (`POST /rfp/tickets` ya devolvía `ticket_id` entero).

**Ruta `/rfp/events`, en un router propio.** `/rfp/tickets/stream` choca
con `GET /rfp/tickets/{ticket_id}` (`ticket_id: int` → 422). El router
propio tampoco arrastra Celery ni los grafos de LangGraph a un endpoint que
solo lee una tabla.

**Estrategia de recuperación elegida: `Last-Event-ID` + replay en
servidor.**
1. El cliente guarda el último `id:` visto (también el del frame de
   apertura).
2. Al reconectar envía `Last-Event-ID: <n>`; el servidor reenvía todo
   `rfp_ticket_events.id > n` (el outbox es persistente: el replay cubre
   caídas de cualquier duración, no solo una ventana corta en memoria).
3. Sin `Last-Event-ID` el stream empieza en "ahora": el estado previo lo
   trae `GET /rfp/tickets`. Para cerrar el hueco entre esa carga inicial y
   el momento en que el stream queda escuchando, la **primera** apertura
   del stream refresca la lista una vez; las reconexiones no refrescan
   nada (de eso se encarga el replay).
4. Un `Last-Event-ID` no numérico se trata como conexión nueva.

**Dedupe por `ticket_id`** (`knownTicketIds` en el panel): un mismo ticket
puede llegar por la lista inicial, por el replay o porque lo subió esa
misma pestaña; en todos los casos aparece una sola vez. Además,
`refreshTicketList` ahora **fusiona** en vez de reemplazar: un ticket que
llega por SSE mientras una respuesta de la lista va en camino no
desaparece.

**Reconexión con backoff progresivo** (`use-rfp-ticket-stream.ts`): primer
reintento a `retry:` del servidor (2 s), luego ×2 por intento hasta 30 s,
con jitter ±20 % (varias pestañas no reconectan en bloque). Al abrir con
éxito el contador vuelve a 0. **Watchdog**: si en 45 s no llega ni un byte
(el servidor manda keep-alive cada 15 s), se aborta y reconecta, porque una
conexión TCP medio muerta no siempre da error. `401/403` no reintenta:
`authFetch` ya cierra la sesión, igual que cualquier otra llamada.

**No se pide la lista entera por evento.** El payload alcanza para pintar
el ticket (`ticketDetailFromEvent`). Lo que sí cambió es el polling de
Hito 9 para los tickets en `analizando`: antes refrescaba **toda** la lista
cada 2 s; ahora pide solo esos tickets (`GET /rfp/tickets/{id}`) para ver
su avance a `analisis_completo` / `descartado`. El stream anuncia la
llegada y el avance de estado sigue por ahí: CONTEXT10.md solo pide
notificar `rfp_ticket_created`.

**Visualmente distinto**: aviso persistente arriba de la lista ("Nueva RFP:
Ticket #17 — Northline Apparel (USA) — Warehouse Operations, Last Mile…",
`aria-live="polite"`), y cada ticket recién llegado con borde de acento,
fondo `--accent-soft` y badge "Nueva" hasta pulsar "Marcar como vistas".
Indicador de conexión en la cabecera: "En vivo" / "Reconectando en Ns
(intento n)" / "Sin sesión". Solo tokens de `:root` (modo oscuro
automático) y `prefers-reduced-motion` respetado.

**El JWT se valida al conectar.** Si expira con el stream abierto, la
conexión sigue hasta el siguiente corte; la reconexión vuelve a validar y,
si ya no es válido, `401` → logout.

## Checklist de la entrega

Backend (`services/`)
- [x] Endpoint SSE que emite un evento por cada ticket de RFP nuevo — `GET /rfp/events`, alimentado por el outbox que escribe `process_rfp_ticket`.
- [x] Nombre de evento explícito `rfp_ticket_created` + payload consistente con `ticket_id` y estado inicial (`analizando`) y el resto de campos de CONTEXT10.md §3.
- [x] Headers y keep-alive — `text/event-stream`, `no-cache`, `keep-alive`, `X-Accel-Buffering: no`, comentario `: keep-alive` cada 15 s.
- [x] Protegido con el mismo JWT del backoffice — sin token o con token inválido: 401.

Frontend (`uis/`)
- [x] Dashboard de RFP refactorizado: la llegada se ve en tiempo real, sin recargar.
- [x] `fetch` + `ReadableStream` con `Authorization: Bearer …` (vía `authFetch`), sin `EventSource`.
- [x] Reconexión con backoff progresivo (2 s → 30 s, jitter) + watchdog de keep-alive.
- [x] Estrategia de recuperación: `Last-Event-ID` + replay en servidor (documentada arriba), dedupe por `ticket_id`.
- [x] Notificación visualmente distinta, sin recargar ni volver a pedir todos los datos por evento.

Pruebas (`tests/`)
- [x] Prueba del endpoint SSE en sí: headers `text/event-stream`, wire con `event: rfp_ticket_created`, `data:` JSON con exactamente los campos del BRIEFING.
- [x] Reconexión + recuperación tras una caída: test automatizado con un uvicorn real que se apaga y vuelve, más la verificación manual de abajo.

## Verificación manual de reconexión + recuperación (UI)

Requisitos: API + worker + backoffice levantados, sesión iniciada, pestaña
en `http://localhost:3000/rfp` con DevTools → Network abierto.

1. **Estado inicial.** El indicador dice **"En vivo"**. En Network hay una
   petición `events` pendiente (`text/event-stream`) con el header
   `Authorization: Bearer …`.
2. **Llegada en vivo.** Subir `rfp-requests/trackflow/trackflow-request-2.pdf`
   desde **otra** pestaña o con `curl -F file=@… POST /rfp/tickets`. En unos
   segundos (lo que tarde el clasificador) aparece el aviso "Nueva RFP:
   Ticket #N — Luna Cosmetics (USA) …" y el ticket arriba de la lista, con
   badge "Nueva". En Network **no** hay un `GET /rfp/tickets` nuevo por ese
   evento.
3. **Caída.** Parar `uvicorn` (Ctrl+C). El indicador pasa a **"Reconectando
   en 2s (intento 1)"**, luego ~4 s (intento 2), ~8 s (intento 3)… En
   Network se ven los reintentos fallidos, cada vez más espaciados.
4. **Tickets durante la caída.** Con la API todavía abajo, crear tickets
   sin pasar por HTTP:
   `cd data/pipelines && .venv/bin/python ../../scripts/rfp_reprocess.py --smoke`
   (3 PDF de muestra: 2 RFP válidas → 2 eventos en el outbox; la tercera se
   descarta y no emite).
5. **Recuperación.** Volver a levantar `uvicorn`. En el siguiente
   reintento el indicador vuelve a **"En vivo"**; la petición `events`
   nueva lleva `Last-Event-ID: <último id>`, y en su respuesta llegan los 2
   `rfp_ticket_created` perdidos (ModaViva, Luna Cosmetics). Los dos
   aparecen resaltados como nuevos.
6. **Sin duplicados.** El ticket del paso 2 sigue apareciendo **una sola
   vez**. Volver a cortar y levantar la API: el replay solo trae eventos
   posteriores al último id, y si el mismo `ticket_id` volviera a llegar,
   el dedupe lo descarta.

## Cómo se verificó

```
$ cd services/incidents-api && uv run --group dev pytest ../../tests/services -q
10 passed                         (3 corridas seguidas, estable)

$ cd data/pipelines && .venv/bin/python -m pytest ../../tests/pipelines/test_rfp_*.py -q
63 passed                         (61 de Hito 9 sin cambios + 2 nuevos)

$ cd uis/backoffice && npx tsc --noEmit -p .        # OK
$ npx eslint src/lib/use-rfp-ticket-stream.ts         # OK
```

Lo que cubre `tests/services/test_rfp_events_stream.py`:

- `401` sin JWT y con JWT inválido (y la respuesta no es `text/event-stream`).
- Headers (`text/event-stream`, `no-cache`, `X-Accel-Buffering`) + wire
  literal `id: … \n event: rfp_ticket_created \n data: {…}` + payload con
  **exactamente** los 7 campos del BRIEFING y sus valores. Nunca
  `event: message`.
- `retry:` + `: keep-alive` cuando no hay eventos.
- Conexión nueva = empieza en "ahora" y el frame de apertura entrega el cursor.
- `Last-Event-ID` → replay exacto de lo posterior; `Last-Event-ID` basura → conexión nueva.
- Entrega **en vivo** contra un uvicorn real (el `TestClient` de Starlette
  bufferiza la respuesta y no sirve para esto): el evento se inserta con la
  conexión ya abierta y llega por ella.
- **Caída real**: uvicorn se apaga con el stream abierto, entran 2 tickets
  con el servidor abajo, el cliente reintenta con backoff creciente (≥2
  intentos fallidos), el servidor vuelve, la reconexión con `Last-Event-ID`
  trae exactamente los 2 perdidos, y el dedupe por `ticket_id` descarta el
  que la UI ya conocía. Sin duplicados.
- `record_ticket_created` idempotente por ticket.

`tests/pipelines/test_rfp_ticket_created_event.py`: con un grafo falso que
reproduce `stream_mode="values"`, el orden real es `classify → announce
(analizando) → warehouse_worker → synthesize`, y un documento descartado no
anuncia nada.

Notas:
- `npx eslint src/components/rfp-intake-panel.tsx` sigue marcando 2 errores
  `react-hooks/set-state-in-effect` **preexistentes** (las líneas
  `void refreshTicketList()` y `void loadApprovalRound(...)` ya los tenían
  en `HEAD`; verificado con la versión de `HEAD`). No se tocaron por estar
  fuera del alcance. El warning de `pollingTicketIds` sin usar desapareció.
- `pytest tests/pipelines` completo tiene 5 errores de colección
  **preexistentes** (módulos no instalados en ese venv:
  `test_agent_*`, `test_rag`, `test_sales_forecast_split`,
  `test_timeseries_cv_order`), iguales con y sin este cambio.
- La verificación manual de la UI (sección anterior) está documentada pero
  no se ejecutó en esta sesión: el contenedor no tiene Postgres ni Redis
  levantados. El protocolo de reconexión que sigue la UI sí está cubierto
  por el test automatizado de caída real.
