# Telemetria TrackFlow — Pipeline de analisis y endpoint de reporte

Fecha: 2026-08-27

Continuacion de `telemetria-almacenamiento-supabase.md` (Fase 1: tabla `telemetry_events`; Fase 2: ingesta real con `POST /telemetry/events`). Este documento cubre la fase siguiente: analizar esos eventos con Pandas y exponerlos como un reporte agregado.

## Desviacion de ruta respecto al enunciado

El enunciado pedia crear `services/telemetry/analysis.py`, pero en este monorepo el backend FastAPI vive entero en `services/incidents-api` (no existe un servicio `services/telemetry` independiente, y el endpoint pedido debe colgar de la misma app FastAPI que ya sirve `/telemetry/events`). El pipeline se creo en `services/incidents-api/telemetry/analysis.py` — mismo subpath relativo (`telemetry/analysis.py`), pero enraizado en el backend real en vez de un servicio inexistente.

## Fase 1 — Pipeline de analisis con Pandas

Archivo: `services/incidents-api/telemetry/analysis.py`

- [x] `load_events(engine, start_date, end_date)` — carga a un DataFrame las filas de `telemetry_events` en la ventana (esta funcion si hace I/O; no es una funcion de metrica).
- [x] Cuatro funciones de metrica, cada una una dimension operacional distinta del catalogo (`telemetry-plan.md` / `event-shcemas.json`), ninguna de negocio:
  - `compute_event_volume` — **volumen**: eventos totales y por `event_type` en la ventana.
  - `compute_error_rate` — **errores**: conteo y tasa de eventos de fallo tecnico (`api_request_failed`, `auth_login_failed`, `frontend_error_captured`) sobre el total.
  - `compute_latency_percentiles` — **latencia**: `mean`/`p50`/`p95`/`p99` de `latency_ms` por `endpoint`, a partir de `api_latency_recorded`.
  - `compute_availability` — **disponibilidad**: % de respuestas no-5xx por `endpoint`, a partir de `api_latency_recorded`.
- [x] Cada funcion de metrica es pura: recibe `(events, start_date, end_date)`, no muta el DataFrame de entrada ni ningun estado externo, y no aplica ninguna ventana por defecto propia — siempre usa la que le pasan. Llamarla dos veces con los mismos argumentos da el mismo resultado.
- [x] Sin loops: todo el calculo usa `.groupby()`, `.agg()`, `.size()`, `.mean()`, `.isin()`, `.quantile()` (dentro de `.agg()`) sobre el DataFrame completo.

## Fase 2 — Endpoint de reporte

`GET /telemetry/report` en `services/incidents-api/routers/telemetry.py`:

- [x] Parametros de query opcionales `start_date` y `end_date` en ISO 8601 (FastAPI/Pydantic los parsea directo a `datetime`). Si faltan: `end_date = ahora (UTC)`, `start_date = end_date - 7 dias`. Fechas naive (sin offset) se asumen UTC.
- [x] El periodo se resuelve una unica vez en el endpoint y se pasa igual a cada funcion de metrica — ninguna aplica su propia ventana.
- [x] Llama a las 4 funciones del pipeline con esos mismos `start_date`/`end_date`.
- [x] Responde:
  ```json
  {
    "period": { "from": "...", "to": "..." },
    "metrics": {
      "volume": { ... },
      "errors": { ... },
      "latency": { ... },
      "availability": { ... }
    }
  }
  ```

## Verificacion realizada

Supabase real no estaba accesible durante esta fase (ver "Bloqueo" abajo), asi que la verificacion se hizo contra un Postgres local efimero (Docker), igual que en fases anteriores:

- 46 eventos sinteticos insertados via el propio `POST /telemetry/events` (30 `api_latency_recorded` con latencias y status codes variados incluyendo 500/502, 5 `api_request_failed`, 3 `auth_login_failed`, 2 `frontend_error_captured`, 4 `route_changed`, 2 `auth_login_succeeded`).
- `GET /telemetry/report` (ventana por defecto de 7 dias) devolvio las 4 dimensiones correctas: volumen total 46 y desglose por tipo, tasa de error 21.74% (10/46), percentiles de latencia por endpoint, disponibilidad 83.33% global y por endpoint.
- Probado tambien con `start_date`/`end_date` explicitos (ventana de 2 horas) y con una ventana sin eventos (año 2000) — responde `200` con metricas en cero/null, sin excepciones.

## Bloqueo detectado: Supabase no responde

Durante esta fase, la connection string guardada en `services/incidents-api/.env` dejo de conectar tanto por el pooler (`tenant/user ... not found`) como por el host directo (DNS no resuelve). Los proyectos gratuitos de Supabase se pausan tras varios dias de inactividad — hay que entrar al dashboard y comprobar si aparece un boton para reactivar el proyecto. Pendiente: en cuanto el proyecto vuelva a estar activo, reverificar que `telemetry_events` tiene al menos 20 filas con variedad de `event_type` (pre-requisito del enunciado) y repetir la prueba de `GET /telemetry/report` contra los datos reales.

## Pendiente segun el propio orden del enunciado

El enunciado indica seguir el orden "funciones de analisis → endpoint de reporte → cache". Cache todavia no esta implementado — es el siguiente paso logico una vez Supabase este disponible de nuevo para confirmar los tiempos de respuesta reales del endpoint.
