# Telemetría TrackFlow — Implementación del pipeline (Fases 1–5)

Fecha: 2026-09-02

Implementación en código de `Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md`
(el diseño de Fases 1–5), siguiendo la guía "Cómo Empezar" del Hito de Data
Pipelines, fase por fase: (1) flow(s) de Prefect con extracción → transformación
→ carga y un paso opcional invocado con `return_state=True`; (2) resiliencia
(retries justificados, manejo explícito de un fallo, caché en la
transformación); (3) idempotencia (carga + log de ejecución); (4) ejecución
como script vía CLI; (5) los tres endpoints de `services/reporting/`.

Probado en local con Prefect 3 (`prefect_test_harness`, sin servidor) y una
base SQLite en memoria: **Supabase sigue pausado** (bloqueo heredado, ver
pendiente #5 del documento de diseño), así que no se pudo probar contra el
proyecto real. El pipeline apunta a Postgres/Supabase en producción; SQLite
solo se usó para poder ejecutar de verdad los tests sin esa base. Igual criterio
para `services/reporting/`: sus 3 endpoints se verificaron con un `TestClient`
+ fakes de `queries`/`load`/`flow` (la correctitud del ETL en sí ya la cubren
los tests de `data/pipelines/`), no contra Supabase real.

## Dónde vive el código

```
data/pipelines/
  pipeline.py                        # punto de entrada principal (CLI)
  PIPELINE_DESIGN.md                 # puntero: cadencia de reporting + comando de ejecución
  pyproject.toml                     # deps: prefect>=3, pandas, sqlalchemy, psycopg2-binary, python-dotenv
  .env.example                       # SUPABASE_DATABASE_URL (o DATABASE_URL)
  exec_weekly_inventory_kpis/
    __init__.py
    flow.py                          # @flow + @task, orquesta extract -> transform -> load
    extract.py                       # extract_inventory_events(), extract_sku_snapshot()
    transform.py                     # normalize_events(), pair_receipt_dispatch(), aggregate_weekly_kpis(), build_weekly_kpis()
    load.py                          # ensure_schema(), stage_kpis(), promote_kpis(), reconcile_dim_sku(), open_run()/close_run(), load_weekly_kpis()
    queries.py                       # read_latest_run(), query_weekly_kpis() -> los usa services/reporting/
    notify.py                        # export_eval_snapshot() -> paso opcional, escribe en data/eval/
    schema.py                        # metadata SQLAlchemy Core (portable Postgres/SQLite, usada por ensure_schema())
    schema.sql                       # DDL Postgres de referencia (reporting.*), para psql/migración
    blocks.py                        # credenciales/config: Prefect blocks si existen, si no env vars
    config.py                        # constantes de dominio (event types, mapeo warehouse->country, nombres de tabla)
  tests/
    test_transform.py                # funciones puras, sin DB
    test_load_sqlite.py              # load.py/extract.py contra SQLite (UPSERT, idempotencia, dedupe)
    test_flow.py                     # @flow real end-to-end (prefect_test_harness), retries/cache/return_state=True/idempotencia

services/reporting/                  # Fase 5: capa HTTP fina, separada de services/incidents-api/
  main.py                            # FastAPI app + CORS, registra el router
  pipeline_path.py                   # agrega data/pipelines/ a sys.path (única forma de importarlo)
  auth.py                            # Bearer/JWT (mismo JWT_SECRET_KEY que incidents-api), decodificado localmente
  schemas.py                         # RunStatusResponse, RunTriggerRequest/Response, WeeklyInventoryKpiRow
  routers/reporting.py               # GET /status, POST /run, GET /kpis -> llaman a data/pipelines/, sin lógica de ETL
  pyproject.toml / requirements.txt  # entorno propio (fastapi, prefect, pandas, sqlalchemy, psycopg2-binary...)
  Dockerfile                         # build context = raíz del repo (necesita data/pipelines/ además de sí mismo)
  .env.example                       # JWT_SECRET_KEY, SUPABASE_DATABASE_URL
```

`exec_weekly_inventory_kpis/` en vez del `exec-weekly-inventory-kpis/` (con
guiones) del documento de diseño: es un paquete Python importable desde
`pipeline.py`, y los guiones no son válidos en un nombre de módulo. El
contenido de cada archivo es el mismo que describe la Fase 4 del diseño.

## Checklist de la entrega (Fase 1 del Hito)

- [x] **Flow(s) de Prefect (`@flow`)** siguiendo extracción → transformación →
  carga: `exec_weekly_inventory_kpis_flow(iso_week=None, trigger="scheduled")`
  en `flow.py`, más `exec_weekly_inventory_kpis_backfill_flow(from_week, to_week)`
  (opcional, Fase 4 del diseño) que llama al flow principal por cada semana ISO.
- [x] **Cada etapa como `@task` independiente**, inputs/outputs explícitos
  (misma tabla que la Fase 4.1 del diseño):

  | Task | Etapa | Input → Output | Retries |
  | --- | --- | --- | --- |
  | `extract_inventory_events` | Extracción | `(engine, week_start, week_end)` → DataFrame de los 5 `event_type` de inventario | 3, backoff `[10, 30, 90]`s |
  | `extract_sku_snapshot` | Extracción | `(engine)` → DataFrame `SELECT * FROM sku` | 3, backoff `[10, 30, 90]`s |
  | `build_weekly_kpis` | Transformación | `(events_df, sku_df, week_start, week_end)` → `(kpis_df, qc)`. Función pura (normalize → enrich → pair → aggregate) | 0 (bug, no reintentar) |
  | `load_weekly_kpis` | Carga | `(engine, kpis_df, sku_df, run_id)` → `(rows_inserted, rows_updated, sku_rows_deactivated)`. Stage + UPSERT transaccional + reconciliación de `dim_sku` | 2 |
  | `finalize_run` | Bookkeeping | contadores + `status` → cierra la fila de `pipeline_runs` | 2 |
  | `export_eval_snapshot` | Opcional / no crítico | `(kpis_df, run_id, iso_week, qc)` → ruta del snapshot en `data/eval/` | 0 |

- [x] **Paso opcional/no crítico invocado con `return_state=True`**:
  `export_eval_snapshot` (`flow.py`, tras `finalize_run`) vuelca el resultado
  de la corrida a `data/eval/exec-weekly-inventory-kpis/<iso_week>_<run_id>.json`
  para validación manual — no es la fuente de verdad (esa es
  `reporting.exec_weekly_inventory_kpis`) y un fallo aquí no debe tirar abajo
  una carga que ya completó:

  ```python
  snapshot_state = export_eval_snapshot(kpis_df, run_id, resolved_iso_week, qc, return_state=True)
  if snapshot_state.is_failed():
      logger.warning("export_eval_snapshot fallo para %s (run_id=%s); reporting.%s ya quedo actualizado.", ...)
  ```

  Verificado en `tests/test_flow.py::test_optional_export_snapshot_failure_does_not_break_the_flow`:
  se fuerza que la task falle y se confirma que el flow igual termina en
  `Completed` y la fila de KPIs quedó cargada.

## Checklist de la entrega (Fase 2 — Resiliencia)

- [x] **`retries` + `retry_delay_seconds` en cada task que toca un servicio
  externo, justificados en un comentario** (`flow.py`, junto a cada `task(...)`):

  | Task | Retries | Por qué |
  | --- | --- | --- |
  | `extract_inventory_events` / `extract_sku_snapshot` | 3, backoff `[10, 30, 90]`s | Contra Supabase: los fallos suelen ser transitorios (drop de conexión, pool agotado), no lógicos. El backoff creciente (~2 min en total) da margen a que la BD se recupere sin martillearla. |
  | `build_weekly_kpis` | 0 | Función pura, sin I/O: un fallo aquí es un bug de la transformación, no algo transitorio — reintentar no lo arregla. |
  | `load_weekly_kpis` | 2, 15s | Idempotente (staging + UPSERT transaccional por clave natural): reintentar es seguro. Menos que extract porque, si se llegó hasta acá, la BD ya respondió una vez; un fallo aquí es más probable que sea real (constraint, disco lleno) que transitorio. |
  | `finalize_run` | 2, 5s | UPDATE de una sola fila, barato de reintentar, pero debe llegar a escribirse sí o sí: es la única fuente de verdad del estado de la corrida (Fase 3.2 del diseño). |
  | `export_eval_snapshot` | 0 | Paso opcional/no crítico; ya se maneja con `return_state=True` (ver Fase 1), así que no necesita reintento automático. |

- [x] **Al menos un fallo de task manejado explícitamente con `return_state=True`**:
  `export_eval_snapshot` (ver Fase 1 más arriba) — reutilizado también para
  este ítem, no hay una segunda instancia distinta.
- [x] **Caché (`cache_key_fn`, `cache_expiration`) en una task de transformación
  costosa**: `build_weekly_kpis` (`flow.py::_weekly_kpis_cache_key`).
  - **Clave de caché** = `pipeline_version` + ventana (`week_start`/`week_end`)
    + huella del contenido de `events_df` (el conjunto ordenado de `event_id`
    presentes — `telemetry_events` es insert-only, así que ese conjunto
    identifica el contenido sin serializar `properties`) + huella de `sku_df`
    (valores completos, porque `SKU` sí es mutable — Fase 2.4 del diseño).
  - **Vigencia**: 1 hora. Dentro de ese margen, un re-run manual o un retry
    que arrastra al flow entero (el `except` de `exec_weekly_inventory_kpis_flow`
    relanza la excepción completa, ver Fase 3 abajo) reutiliza el cálculo en
    vez de repetir el join + emparejamiento inbound/outbound. Pasada 1 hora se
    asume que pudo llegar telemetría nueva dentro de la ventana de gracia y se
    recalcula.
  - Verificado en `tests/test_flow.py::test_weekly_kpis_cache_key_is_stable_for_identical_inputs_and_changes_with_data`
    (misma clave para inputs idénticos; clave distinta si cambia un `event_id`
    o si cambia un campo mutable de `SKU`).

## Checklist de la entrega (Fase 3 — Idempotencia)

- [x] **La carga es idempotente**: correr el pipeline dos veces sobre el mismo
  rango deja el mismo resultado en `reporting.exec_weekly_inventory_kpis`
  (UPSERT transaccional por la clave natural `(iso_week, warehouse, client_id)`,
  Fase 3.1 del diseño — ya implementado en la entrega de Fase 1, no es código
  nuevo). Verificado explícitamente a nivel de flow completo (no solo de la
  task de carga) en
  `tests/test_flow.py::test_flow_is_idempotent_on_rerun_over_the_same_week`:
  corre `exec_weekly_inventory_kpis_flow` dos veces seguidas sobre `2026-W35`
  y confirma que sigue habiendo **una sola fila** con los mismos
  `fulfillment_rate`/`outbound_qty` después de ambas corridas — solo cambia
  `pipeline_run_id` (bookkeeping de qué corrida escribió la fila por última
  vez, no el resultado de negocio).
- [x] **Metadata mínima de cada corrida registrada en base de datos**:
  `reporting.pipeline_runs` (`load.open_run()` / `load.close_run()`, ya
  implementado en la entrega de Fase 1) — `started_at`, `finished_at`,
  `rows_read`/`rows_rejected`/`rows_transformed`/`rows_upserted_*`, `status`
  (`running`/`completed`/`failed`) y `error_message`/`error_sample` si algo
  falló. Detalle de cada campo y por qué existe: Fase 3.2 del documento de
  diseño.

## Checklist de la entrega (Fase 4 — Ejecución basada en script)

- [x] **`data/pipelines/pipeline.py` ejecutable directamente como CLI**
  (`if __name__ == "__main__":`, ya implementado en la entrega de Fase 1):
  soporta `--iso-week`, `--from-week`/`--to-week` (backfill) y sin argumentos
  (última semana ISO cerrada).
- [x] **`python data/pipelines/pipeline.py` corre sin errores de código**:
  verificado — llega hasta `blocks.get_engine()` y falla con un
  `RuntimeError` explícito y controlado (`"No hay conexion a Supabase
  configurada..."`), no con una traza rota. Es el comportamiento esperado en
  este entorno porque Supabase sigue pausado (mismo bloqueo que en la entrega
  de Fase 1); el pipeline completo (extract → transform → load) sí se
  verificó de punta a punta contra SQLite en `tests/test_flow.py`, que
  ejercita el mismo código de `@flow`/`@task`.
- [x] **Cadencia de reporting + comando de ejecución documentados en
  `data/pipelines/PIPELINE_DESIGN.md`**: semanal, corrida el lunes procesando
  la semana ISO recién cerrada (con ventana de gracia de 7 días); comandos
  `uv run pipeline.py [--iso-week ... | --from-week ... --to-week ...]`. Ver
  ese archivo.

## Checklist de la entrega (Fase 5 — Endpoints del backend)

Nuevo servicio `services/reporting/` (sibling de `services/incidents-api/`,
Fase 5.1 del diseño), registrado en `docker-compose.yml` (`reporting`,
puerto `8010`).

- [x] **Tres endpoints en `services/reporting/`, en su propio módulo**
  (`routers/reporting.py`, separado de `services/incidents-api/telemetry/`):

  | Endpoint | Qué hace | Auth |
  | --- | --- | --- |
  | `GET /reporting/exec-weekly/status` | Última corrida (`queries.read_latest_run`): `run_id`, `pipeline_version`, `iso_week`, `status`, `started_at`, `finished_at`, `rows_read`, `rows_rejected`, `rows_unmatched_sku`. | Cualquier usuario autenticado. |
  | `POST /reporting/exec-weekly/run` | Body opcional `{iso_week}`. Abre la fila de `pipeline_runs` **de forma síncrona** (`load.open_run`, misma ventana que calcula `flow.resolve_extraction_window`) para devolver `run_id` ya mismo, y lanza `exec_weekly_inventory_kpis_flow(..., run_id=run_id)` en background (`BackgroundTasks`) — el request nunca ejecuta ETL en el proceso web. Responde `202 Accepted`. | Roles `admin`/`manager` únicamente (403 para el resto) — "un director que quiere refrescar el consolidado" (diseño, Fase 5.1), no cualquier usuario. |
  | `GET /reporting/exec-weekly/kpis` | Filtra `from_week`, `to_week`, `warehouse`, `country`, `client_id` sobre `queries.query_weekly_kpis` — solo lectura, nunca recalcula. | Cualquier usuario autenticado. |

- [x] **Los endpoints importan flows/funciones desde `data/pipelines/` sin
  duplicar lógica**: `routers/reporting.py` importa `flow`, `load`, `queries`
  y `blocks.get_engine` de `exec_weekly_inventory_kpis` (vía `pipeline_path.py`,
  que agrega `data/pipelines/` a `sys.path` porque no está instalado como
  paquete — ver "Decisiones de implementación" más abajo). Se agregó
  `flow.resolve_extraction_window()` como función compartida (antes vivía
  inline dentro del flow) precisamente para que el endpoint no repitiera el
  cálculo de la ventana de gracia.
- [x] **Mismas convenciones de autenticación que el resto de la API**:
  Bearer/JWT con el mismo `JWT_SECRET_KEY` que `services/incidents-api`
  (`auth.py`) — incidents-api emite el token en el login y lo resuelve
  contra su tabla de usuarios; `services/reporting/` no es dueño de esa
  tabla, así que decodifica el JWT localmente (misma firma, mismo esquema
  401/`WWW-Authenticate: Bearer`) en vez de repetir esa consulta.
- [x] **Forma de la respuesta de `GET /kpis` == esquema de
  `reporting.exec_weekly_inventory_kpis`**: `WeeklyInventoryKpiRow`
  (`schemas.py`) tiene exactamente las columnas de la Fase 2.5 del diseño —
  no hay un `CONTEXT-company.md` real del que copiar un contrato distinto
  (mismo pendiente heredado, ver más abajo).

Verificado con `fastapi.testclient.TestClient` + fakes de `queries`/`load`/`flow`
(sin Supabase real, mismo motivo que el resto de esta entrega): `401` sin
token, `403` con rol `viewer` en `POST /run`, `202` con rol `manager` (y el
`run_id` que se devuelve es el mismo que `open_run` creó, no uno nuevo), `200`
con la forma esperada en `/status` y `/kpis`.

## Cómo se instaló Prefect 3

```bash
cd data/pipelines
uv add "prefect>=3"
```

En este entorno no había `uv` disponible, así que se creó el `pyproject.toml`
a mano (mismas dependencias que generaría `uv add`) y se instaló con
`pip install -e .[dev]` dentro de un venv (`data/pipelines/.venv/`, ignorado
por `.gitignore`) para poder ejecutar los tests de verdad.

## Decisiones de implementación no cubiertas por la guía genérica

- **`data/raw/` y `data/process/`**: este pipeline lee directo de Postgres
  (Supabase) en cada corrida — no hay archivos intermedios que aterricen en
  `data/raw/` ni scripts de transformación reutilizables fuera del paquete
  (la transformación ya vive en `transform.py`, importable). Quedan sin uso
  por este pipeline; se documenta para que quede explícito, no es un olvido.
- **`data/eval/`**: usado por el paso opcional (`export_eval_snapshot`), un
  archivo JSON por corrida con los KPIs calculados + contadores de calidad
  (`rows_read`, `rows_rejected`, `rows_unmatched_sku`, `error_sample`).
- **`CONTEXT-company.md`**: sigue sin existir en el repo (igual que cuando se
  escribió el diseño). Los valores derivados de esa sección no cambiaron.
- **Portabilidad Postgres/SQLite en `load.py`**: SQLite no acepta el
  `upsert-clause` (`ON CONFLICT ... DO UPDATE`) después de un
  `INSERT ... SELECT` (solo después de `INSERT ... VALUES`); Postgres sí. Para
  poder probar `promote_kpis` de verdad sin Supabase, la promoción trae las
  filas de staging a Python y arma el INSERT con `sqlalchemy.dialects.postgresql.insert`
  o `sqlalchemy.dialects.sqlite.insert` según el dialecto — mismo UPSERT
  atómico de una sola sentencia en ambos motores, portable para tests.
- **`services/reporting/` importa `data/pipelines/` por `sys.path`, no como
  paquete instalado** (`pipeline_path.py`). Se evaluó declarar
  `exec_weekly_inventory_kpis` como dependencia local editable de
  `services/reporting/pyproject.toml` (vía `uv`), pero se descartó: ningún
  otro servicio del monorepo usa ese patrón (cada uno gestiona su propio
  entorno completo, con dependencias duplicadas si hace falta — ver
  `services/incidents-api/requirements.txt`), y una instalación editable
  cross-directorio complica el build de Docker sin aportar nada que
  `sys.path.insert` no resuelva ya de forma explícita y fácil de depurar. El
  costo es que `services/reporting/requirements.txt` repite `prefect`,
  `pandas`, `sqlalchemy`, `psycopg2-binary` — mismo trade-off que ya existe
  entre `incidents-api` y `data/pipelines/` (ambos declaran `pandas`/
  `psycopg2-binary` por separado).
- **`POST /reporting/exec-weekly/run` corre el flow con `BackgroundTasks` de
  FastAPI, no con un deployment de Prefect (`run_deployment`)**, como sí
  proponía el diseño (Fase 5.1: *"deployment run asíncrono"*). No hay
  Prefect server/Cloud target configurado en este entorno (pendiente #3 más
  abajo), así que no hay deployment que disparar. `BackgroundTasks` cumple el
  mismo contrato observable (`202` inmediato con `run_id`, ETL fuera del
  request-response) pero corre en el mismo proceso web, no en un worker de
  Prefect separado — swap directo a `run_deployment(...)` en cuanto exista un
  deployment registrado, sin tocar el resto del endpoint.

## Pendiente / siguientes pasos

1. Reactivar el proyecto Supabase pausado y correr `exec_weekly_inventory_kpis_flow`
   (y `services/reporting/` contra él) con datos reales — hasta ahora todo
   probado con SQLite/fakes + datos sintéticos.
2. Deployment de Prefect (`prefect deploy` / schedule semanal) — hoy el flow
   solo se ejecuta manualmente vía `pipeline.py`, import directo, o
   `POST /reporting/exec-weekly/run`. En cuanto exista, cambiar ese endpoint
   de `BackgroundTasks` a `run_deployment(...)` (ver más arriba).
3. Cablear `inventory_discrepancy_detected` y `direct_stock_edit_rejected` en
   el frontend (pendiente heredado del diseño): sin ellos,
   `discrepancy_frequency` y `governance_flags` siguen saliendo a cero contra
   datos reales.
4. Registrar los Prefect blocks (`trackflow-supabase`, `reporting-pipeline-config`)
   una vez haya un Prefect server/Cloud target; hoy `blocks.py` cae a
   `data/pipelines/.env` porque no hay ninguno registrado.
5. `services/reporting/` no tiene tests automatizados en el repo (se verificó
   con un script manual de smoke-test, no comiteado — ningún otro servicio
   del monorepo tiene carpeta `tests/` tampoco, así que no se introdujo un
   patrón nuevo sin precedente); si se agrega, debería ir en
   `services/reporting/tests/` con `TestClient` + los mismos fakes de
   `queries`/`load`/`flow` usados para verificar esta entrega.
