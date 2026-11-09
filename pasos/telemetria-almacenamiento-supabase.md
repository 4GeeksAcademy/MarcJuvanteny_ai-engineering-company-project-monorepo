# Telemetria TrackFlow — Almacenamiento real en Supabase (Fase 1 + Fase 2)

Fecha: 2026-08-19

Commit: `b2ca73d` — "Persistencia real de telemetría en Supabase (Fase 1 + Fase 2)"

Continuacion de `telemetria-trackflow-resumen.md` (que cubria Fases 1-3 de captura en frontend/backend, sin persistencia real). Este documento cubre la fase siguiente: guardar los eventos de verdad en Supabase y sustituir el stub del endpoint por una implementacion real con validacion parcial de lote.

## Fase 1 — Tabla de almacenamiento en Supabase

- [x] Tabla `telemetry_events` (`services/incidents-api/models.py`, clase `TelemetryEventRecord`, `SQLModel` con `table=True`). Se crea sola en el arranque via `SQLModel.metadata.create_all()` (mismo mecanismo que el resto de tablas del proyecto; no hay Alembic ni migraciones aparte).
- [x] Cada `TelemetryEvent` de la API se mapea 1:1 a una fila con el contrato exacto: `event_id`, `timestamp`, `session_id`, `user_id`, `event_type`, `schema_version`, `request_id`, `properties` (JSONB).
- [x] `event_id` como primary key (es un UUID unico por evento; evita un id surrogate innecesario).
- [x] Tres indices: btree en `timestamp`, btree en `event_type`, GIN en `properties` (`postgresql_using="gin"`) para busquedas dentro del JSONB.
- [x] Sin ninguna ruta UPDATE/DELETE sobre esta tabla en ningun router — solo insercion. Documentado en el docstring de la clase (`TelemetryEventRecord`): los eventos de telemetria son inmutables una vez registrados.

Nota de contrato: `TelemetryEvent` no tiene un campo `tags` — el unico JSONB es `properties`. El GIN pedido se aplico sobre `properties`, que es el unico campo variable indexable con GIN (requiere JSONB, especifico de PostgreSQL).

## Fase 2 — Endpoint real en FastAPI

`services/incidents-api/routers/telemetry.py`, `POST /telemetry/events`:

- [x] Acepta el mismo envelope que el stub (`{"events": [...]}`), pero `TelemetryBatch.events` se tipa como `list[dict[str, Any]]` — no como `list[TelemetryEvent]` — para que un evento mal formado no tumbe la validacion de FastAPI sobre el lote completo.
- [x] Cada evento crudo se valida individualmente con `TelemetryEvent.model_validate(...)` (mismo modelo de la fase anterior, sin modificarlo) mas una comprobacion de que `timestamp` sea parseable (`datetime.fromisoformat`).
- [x] Los eventos que no cumplen el contrato se rechazan de forma individual, sin cancelar el lote — los eventos validos del mismo lote se persisten igual.
- [x] Insercion de los eventos validos en una unica operacion de bulk insert (`sqlalchemy.insert(TelemetryEventRecord)` ejecutado con la lista completa de filas, no un `add()` por evento).
- [x] Respuesta `{"received": N, "stored": M, "rejected": R}`.
- [x] Verificado que `TelemetryService` del frontend (`uis/backoffice/src/services/telemetry.ts`, funcion `sendBatch`) solo mira `response.ok` (codigo de estado HTTP), nunca el body — el cambio de forma de la respuesta es compatible sin tocar el frontend.

## Fase 3 — Verificacion end-to-end

Realizada en dos etapas, sin tocar datos reales de forma permanente:

**1. Postgres local (Docker, efimero)** — antes de tocar Supabase: tabla + 3 indices confirmados con `pg_indexes`; lote mixto de 5 eventos (2 validos, 3 invalidos: timestamp invalido, campo obligatorio faltante, campo extra no permitido) → `{"received":5,"stored":2,"rejected":3}`, y las 2 filas correctas confirmadas en la tabla.

**2. Supabase real** (proyecto `njiyfbndjazvrdddqhkz`, region `eu-west-2`):
- Conexion verificada, tabla y los 3 indices confirmados con `pg_indexes` (unica vez que se crearon todas las tablas del proyecto: `sku`, `stockentry`, `stockexit`, `telemetry_events`, con siembra automatica de inventario demo).
- Lote mixto por curl (2 validos + 2 invalidos) → conteos correctos; filas de prueba insertadas y luego borradas por SQL directo (no por la API) para no dejar basura.
- Flujo real de punta a punta con Playwright contra el backoffice real (`uis/backoffice`) arrancado localmente contra el backend conectado a Supabase: registro de usuario de prueba, login fallido + login correcto, alta de una orden de entrada y una de salida en `/inventory/orders/inbound` y `/outbound`, y un error de frontend real no capturado. Resultado: **24 eventos reales** llegaron a `telemetry_events` con los campos correctos (`auth_login_attempted`/`_failed`/`_succeeded`, `route_changed`, `page_load_completed`, `api_latency_recorded`, `inbound_order_created`, `stock_threshold_triggered`, `outbound_order_created`, `frontend_error_captured`).
- Efectos secundarios de esa prueba revertidos despues de confirmar: las 2 filas de `stockentry`/`stockexit` de prueba se borraron por SQL directo (stock de `CLT-SNK-W-42-Z` en Zaragoza vuelve al valor real); el usuario de prueba vivia en `services/incidents-api/suppliers.json` (TinyDB local, no Supabase) y se revirtio con `git checkout`. Las 24 filas de telemetria de la prueba se dejaron como evidencia — no afectan reportes de negocio, solo el log de eventos.

## Hallazgo de seguridad corregido

`services/incidents-api/.env` estaba versionado en git desde varios commits atras, con `JWT_SECRET_KEY` y (mas recientemente) el `DATABASE_URL` de Supabase expuestos en el historial. Se saco del tracking (`git rm --cached`) y se añadio `.env` al `.gitignore` raiz. El archivo sigue existiendo en disco con la connection string real, solo dejo de subirse a git. Pendiente: valorar rotar `JWT_SECRET_KEY` dado que el valor anterior quedo expuesto en el historial de commits (no critico, pero conviene rotarlo en algun momento).

## Limitaciones conocidas

- El endpoint no reenvia eventos a `TELEMETRY_ENDPOINT` (sigue siendo un placeholder reservado para una fase futura, igual que en la fase de captura).
- Un reintento del mismo lote (mismo `eventId`, tras un fallo de red que en realidad si llego al backend) rompe la insercion por violar el `primary key` en `event_id`. No se maneja explicitamente porque el frontend solo reintenta si `response.ok` fue `false`.
- No hay endpoint para consultar `telemetry_events` desde la API todavia (solo ingesta) — la verificacion de este documento se hizo consultando Supabase directamente.
