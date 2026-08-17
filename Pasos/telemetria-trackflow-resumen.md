# Telemetria TrackFlow — Fase 1, 2 y 3

Fecha: 2026-08-17

Implementacion completa del plan de telemetria (`telemetry-plan.md` + `event-shcemas.json`). Todo lo listado abajo esta implementado y probado en local (backend + frontend arrancados juntos, login real, navegacion, alta de inventario, cierre de pestaña).

## Fase 1 — Backend: endpoint de telemetria

- [x] `POST /telemetry/events` en `services/incidents-api/routers/telemetry.py` — acepta `{ "events": [...] }`, loggea cantidad + `event_type` de cada evento, responde `{"received": N}`.
- [x] Modelo Pydantic `TelemetryEvent` (`extra="forbid"`) con el envelope exacto: `eventId`, `timestamp`, `sessionId`, `userId`, `event_type`, `schemaVersion`, `requestId`, `properties`.
- [x] `TELEMETRY_ENDPOINT` leida desde entorno en `routers/telemetry.py` (sin usarse aun — placeholder para reenvio futuro). Añadida a `.env.example` y `.env`.
- [x] Router registrado en `main.py`. Endpoint publico (sin `Depends(get_current_user)`), necesario para eventos pre-login.
- [x] CORS: se añadio `allow_credentials=True` en `main.py` — sin esto, `navigator.sendBeacon` (que siempre manda credenciales en cross-origin) fallaba el preflight. Detectado y corregido durante las pruebas.

## Fase 2 — Frontend: `TelemetryService`

Archivo: `uis/backoffice/src/services/telemetry.ts`

- [x] Cola en memoria + batch: flush a los 10s desde el primer evento encolado, o al llegar a 20 eventos (lo que ocurra primero).
- [x] Flush normal por `fetch` a `NEXT_PUBLIC_TELEMETRY_ENDPOINT` (fallback: `${API_BASE_URL}/telemetry/events`).
- [x] Flush por `navigator.sendBeacon` en `visibilitychange` → `hidden`.
- [x] Reintentos con backoff exponencial (hasta 3) antes de descartar el lote.
- [x] `track(eventType, properties)` — unica funcion publica; autocompleta `eventId`, `requestId`, `timestamp`, `sessionId`, `userId`, `schemaVersion`.
- [x] `timedFetch()` — wrapper interno que instrumenta cualquier llamada HTTP existente con `api_latency_recorded`/`api_request_failed`, plantillando el endpoint (sin ids ni query).

## Fase 3 — Instrumentacion

### Piso tecnico transversal (toda la app)

- [x] Errores no capturados: `components/global-error-listener.tsx` (`window.onerror` + `unhandledrejection`), `components/error-boundary.tsx` (React error boundary), `app/global-error.tsx` (crash de root). Los tres emiten `frontend_error_captured`.
- [x] Rendimiento + navegacion: `components/route-tracker.tsx` (montado en `app/layout.tsx`) emite `page_load_completed` y `route_changed` en cada cambio de ruta.

### Eventos de negocio cableados (13 de 15)

| Evento | Disparador |
| --- | --- |
| `auth_login_attempted` / `_succeeded` / `_failed` | `lib/auth-context.tsx` → `login()` (usado por login y registro) |
| `session_expired` | `lib/auth-context.tsx` → `authFetch()` en un 401 |
| `protected_route_redirected` | `components/auth-guard.tsx` |
| `route_changed` | `components/route-tracker.tsx` |
| `page_load_completed` | `components/route-tracker.tsx` |
| `api_latency_recorded` / `api_request_failed` | `timedFetch()`, usado por `authFetch` (cubre inventario, incidencias, proveedores, cuenta) y por los 3 formularios publicos (registro, olvide/reset contrasena) |
| `inbound_order_created` | `components/inventory-inbound-order-panel.tsx` |
| `outbound_order_created` | `components/inventory-outbound-order-panel.tsx` |
| `stock_threshold_triggered` | Ambos paneles de ordenes, tras crear la orden, si `current_stock <= LOW_STOCK_THRESHOLD` (constante movida a `lib/inventory.ts`) |
| `frontend_error_captured` | Los tres puntos del piso tecnico |

## Eventos NO cableados (2 de 15)

Decision confirmada con el usuario: no fabricar datos falsos para cumplir el schema.

- **`direct_stock_edit_rejected`** — no existe ninguna funcionalidad de edicion directa de stock en la app (ni en frontend ni en backend); el stock es siempre derivado de altas/bajas. No hay disparador real.
- **`inventory_discrepancy_detected`** — no existe deteccion automatica de discrepancias. Lo unico relacionado es una categoria de incidencia manual (`inventory_discrepancy`) que no recoge los campos que exige el evento (`expected_stock`, `counted_stock`, `audit_id`).

Ambos quedan como deuda tecnica: requieren construir la funcionalidad de negocio correspondiente antes de poder instrumentarlos honestamente.

## Limitaciones conocidas

- `userId` = email del usuario autenticado (o `"anonymous"`) — `/auth/me` no expone hoy un id opaco.
- `navigation_source` en `route_changed` queda fijo en `"programmatic"` — distinguir clic de sidebar vs. navegacion programada de forma fiable no era viable sin mas cambios.
- `client_id` en los eventos de inventario usa el nombre del cliente (`client_name`) — el modelo `SKU` no tiene un id de cliente separado.
- El backend no valida los eventos contra el allowlist por tipo de `event-shcemas.json` todavia (Fase 1 solo valida el envelope) — validacion estricta queda para una fase futura, tal como indica `telemetry-plan.md`.
- `expired_by` en `session_expired` se fija en `"invalid_token"` como aproximacion generica — un 401 desde `authFetch` no distingue TTL vencido de token revocado.

## Verificacion realizada

Backend + frontend arrancados en local (con `DATABASE_URL` apuntando a un SQLite temporal solo para la prueba, ya que la Supabase real no es alcanzable desde este entorno). Con Playwright:
- Login real de un usuario de prueba → `auth_login_attempted`/`auth_login_succeeded` disparados.
- Navegacion SPA por sidebar entre 4 secciones → `route_changed`/`page_load_completed` por cada cambio, todo en **un solo POST batcheado** de 19 eventos (no uno por evento).
- Alta de una orden de entrada de inventario → `inbound_order_created` + `api_latency_recorded` correctos.
- Visita sin sesion a una ruta protegida → redirigido a `/login` + `protected_route_redirected`.
- Error lanzado manualmente + promesa rechazada sin capturar → dos `frontend_error_captured`.
- Ocultar la pestaña (`visibilitychange` → `hidden`) → lote pendiente enviado por `sendBeacon`, 200 OK, cero errores de consola.
- `npm run build`, `npx tsc --noEmit` y `npx eslint src` limpios en el frontend.
