# Telemetría TrackFlow — Exportación nocturna + control de jobs (`nightly_export`)

Fecha: 2026-09-04

Implementación de la guía de "Exportación nocturna + control de estado de
jobs": tabla `job_runs` (control de scheduling, separada de
`reporting.pipeline_runs` del pipeline de KPIs — ver
`Pasos/telemetria-pipeline-implementacion.md`), script `scripts/nightly_export.py`
que exporta telemetría del día + dispara el pipeline, lock e idempotencia vía
`job_runs`, módulo `job_runner` en `services/`, y la expresión cron.

## Nota de arquitectura: `ops.job_runs` vs `reporting.pipeline_runs`

Son capas distintas a propósito, no se fusionan:

| | `reporting.pipeline_runs` (Hito 6) | `ops.job_runs` (esta entrega) |
| --- | --- | --- |
| Qué registra | Una corrida de **un pipeline concreto**: `exec_weekly_inventory_kpis_flow` | Una corrida de **cualquier job de scheduling** (hoy solo `nightly_export`) |
| Grano | `iso_week` (semana) | `target_date` (día) |
| Quién la escribe | `data/pipelines/exec_weekly_inventory_kpis/load.py` (`open_run`/`close_run`), desde dentro del `@flow` | `services/job_runner/runner.py`, desde `scripts/nightly_export.py` (fuera del pipeline) |
| Columnas | `rows_read`, `rows_rejected`, `sku_snapshot_rows`, etc. — específicas de ese ETL | `job_name`, `target_date`, `status`, `error_message` — genéricas, sirven para cualquier job futuro |

`nightly_export.py` **usa** el pipeline del Hito 6 (lo lanza como subproceso)
pero no es ese pipeline: es la capa de scheduling por encima. Una corrida de
`nightly_export` crea/actualiza una fila en `job_runs`; el pipeline que lanza
como subproceso crea/actualiza su propia fila en `pipeline_runs`, de forma
independiente.

## Dónde vive el código

```
services/job_runner/                 # módulo de control de estado (Fase "Control de estado")
  config.py                          # JOB_RUNS_SCHEMA="ops", JOB_RUNS_TABLE, NIGHTLY_EXPORT_JOB_NAME
  db.py                               # get_engine() -> SUPABASE_DATABASE_URL/DATABASE_URL (sin Prefect)
  schema.py                           # tabla ops.job_runs (SQLAlchemy Core, portable Postgres/SQLite)
  schema.sql                          # DDL Postgres de referencia (psql -f)
  runner.py                           # ensure_schema(), has_processing_lock(), has_completed_for_date(),
                                       # start_job_run(), mark_completed(), mark_failed(), get_latest_job_run()
  pyproject.toml / requirements.txt   # sqlalchemy, psycopg2-binary, python-dotenv, pandas
  .env.example
  tests/test_runner.py                # contra SQLite en memoria

scripts/nightly_export.py            # script principal (Fase "Script principal")
infra/nightly_export.cron            # expresión cron + justificación del horario
```

Módulos **flat** dentro de `services/job_runner/` (`config.py`, `db.py`,
`schema.py`, `runner.py`, sin `__init__.py` ni imports relativos) — mismo
patrón que `services/incidents-api/` (`database.py`, `models.py`, etc., sin
paquete envolvente), no el patrón de paquete con imports relativos que usa
`data/pipelines/exec_weekly_inventory_kpis/`. `scripts/nightly_export.py` lo
importa igual que `scripts/seed_incidents.py` importa de
`services/incidents-api/`: `sys.path.insert(0, ".../services/job_runner")` +
imports absolutos (`import runner as job_runner`).

## Checklist de la entrega — Modelo de datos

- [x] **Tabla `job_runs`** con `id`, `job_name`, `target_date`, `status`
  (`pending`/`processing`/`completed`/`failed`), `started_at`, `finished_at`,
  `error_message`, `created_at` (`services/job_runner/schema.py`).
- [x] **Índice en `(job_name, target_date)`** — consultas de idempotencia
  (`has_completed_for_date`) sin escanear toda la tabla.
- [x] **Migración/DDL**: `services/job_runner/schema.sql` (Postgres, para
  `psql -f` o una migración real) + `ensure_schema()` en `runner.py`
  (`CREATE TABLE IF NOT EXISTS`, idempotente, misma metadata SQLAlchemy Core
  que genera el DDL — mismo patrón que `ensure_schema()` del pipeline de
  KPIs). Esquema `ops` (nuevo, separado de `reporting` y del esquema público
  de `telemetry_events`/`sku`) — namespacing por capa: dominio (público) /
  analítica (`reporting`) / orquestación (`ops`).
- [x] **No fusionar `job_runs` con `pipeline_runs`** — ver la nota de
  arquitectura arriba; son módulos y tablas completamente separados.

## Checklist de la entrega — Script principal (`scripts/nightly_export.py`)

- [x] **`target_date` desde `TARGET_DATE` o ayer en UTC por defecto**
  (`resolve_target_date()`).
- [x] **Exporta `telemetry_events` del día a `data/raw/telemetry_<target_date>.csv`,
  solo si el archivo no existe** (`export_telemetry_csv()`). Explícitamente
  un snapshot de backup/auditoría: el pipeline sigue leyendo de la base, no
  de este CSV.
- [x] **Lanza el pipeline de datos como subproceso tras la exportación**
  (`run_pipeline_subprocess()`) — **adaptación del comando de referencia**:
  en vez del genérico `python -m data.pipelines.telemetry_kpi_daily.run
  --no-prefect`, usa el entry point real del Hito 6,
  `data/pipelines/pipeline.py --iso-week <semana> --trigger scheduled`. Como
  ese pipeline es **semanal** (`iso_week`), no diario, `target_date` se
  traduce a la semana ISO que lo contiene (`iso_week_for()`): correrlo cada
  noche mantiene "al día" la semana en curso sin duplicar nada (el pipeline
  ya es idempotente por `(iso_week, warehouse, client_id)`, Fase 3 de esa
  entrega). El lunes-noche esa misma corrida cierra definitivamente la
  semana recién terminada.
- [x] **Escribe en `job_runs` el resultado**: `start_job_run()` al principio
  (`processing`), `mark_completed()`/`mark_failed(..., error_message)` al
  final, según el subproceso haya terminado con `returncode == 0` o no.
- [x] **Ejecutable desde línea de comandos**: `python scripts/nightly_export.py`
  (`if __name__ == "__main__":`).

## Checklist de la entrega — Idempotencia y bloqueo

- [x] **Lock vía `processing`, sin tabla/columna aparte**: `has_processing_lock()`
  es el chequeo rápido antes de intentar arrancar; el bloqueo real es un
  **índice único parcial** sobre la propia `job_runs`
  (`ux_job_runs_processing_lock` — `UNIQUE (job_name) WHERE status = 'processing'`,
  `schema.py`/`schema.sql`). Un segundo `INSERT` con `status='processing'`
  para el mismo `job_name` viola esa constraint → `IntegrityError` →
  `runner.start_job_run()` lo traduce a `JobLockHeldError` → el script
  cancela sin marcar `failed` (no es un error del job, es la carrera
  esperada). Esto cierra la condición de carrera entre "chequear" e
  "insertar" que un `has_processing_lock()` aislado no puede cerrar por sí
  solo. Verificado en
  `tests/test_runner.py::test_start_job_run_sets_processing_and_lock_blocks_a_second_start`
  (SQLite también soporta índices parciales, así que el mismo mecanismo se
  prueba de verdad, no solo se simula).
- [x] **Idempotencia vía `target_date`**: `has_completed_for_date(job_name, target_date)`
  — un `job_name` sin `target_date` no alcanza (`get_latest_job_run` solo
  informa la última corrida, no decide idempotencia). Si ya hay `completed`
  para ese par exacto, el script no reexporta el CSV ni relanza el pipeline
  y solo imprime la omisión. Verificado end-to-end (smoke test, ver abajo):
  con una fila `completed` preexistente, `main()` no toca el filesystem ni
  invoca el subproceso.

## Checklist de la entrega — Control de estado (`services/`)

- [x] **Módulo `job_runner`** (`services/job_runner/runner.py`) con
  `ensure_schema`, `has_processing_lock`, `has_completed_for_date`,
  `start_job_run`, `mark_completed`, `mark_failed`, `get_latest_job_run` —
  sin ningún `job_name` hardcodeado dentro del módulo (lo pasa el llamador),
  así que sirve para cualquier job futuro, no solo `nightly_export`.

## Cómo se verificó

Igual que el resto de esta serie: Supabase sigue pausado, así que no hay
prueba contra el proyecto real.

- `services/job_runner/tests/test_runner.py` (5 tests, `pytest`) contra
  SQLite en memoria: lock, idempotencia por fecha, `mark_completed`/`mark_failed`,
  y que jobs con distinto `job_name` no comparten el lock.
- `scripts/nightly_export.py` en sí **no tiene tests automatizados en el
  repo** (mismo motivo que `services/reporting/`: ningún script/servicio del
  monorepo trae `tests/` junto al código que golpea Supabase directo salvo
  `data/pipelines/`). Se verificó con un script manual de smoke-test (no
  comiteado) que corre `main()` de verdad contra SQLite + un subproceso
  **real** de `data/pipelines/pipeline.py`, tres escenarios:
  1. Corrida normal: exporta el CSV, lanza el subproceso, el subproceso
     falla (Supabase no configurado) → `job_runs` queda `failed` con el
     `stderr` real del subproceso como `error_message`, y el script
     propaga la excepción (`exit != 0`, para que cron lo marque como fallo).
  2. Lock: con una fila `processing` preexistente, `main()` cancela sin
     tocar esa fila ni el filesystem.
  3. Idempotencia: con una fila `completed` preexistente para el mismo
     `target_date`, `main()` cancela sin reexportar el CSV ni relanzar el
     pipeline.

## Decisiones de implementación no cubiertas por la guía genérica

- **Esquema `ops`** para `job_runs`: no estaba especificado; se eligió para
  no mezclarlo ni con el esquema público (`telemetry_events`/`sku`, datos de
  dominio) ni con `reporting` (analítica del pipeline de KPIs) — ver la nota
  de arquitectura arriba.
- **Grano diario vs. pipeline semanal**: la guía genérica asume un pipeline
  diario (`telemetry_kpi_daily`); el Hito 6 real es semanal. Se optó por
  traducir `target_date` a su semana ISO en vez de forzar al pipeline a un
  grano que no tiene — ver el checklist de "Script principal" arriba.
- **Intérprete del subproceso**: `data/pipelines/` tiene su propio venv
  (deps: `prefect`, `pandas`, `sqlalchemy`, `psycopg2-binary`), distinto del
  de `job_runner`. `run_pipeline_subprocess()` usa
  `data/pipelines/.venv/bin/python` si existe, si no cae al intérprete que
  corre el propio script — mismo trade-off de entornos separados que ya
  existe entre `services/reporting/` y `data/pipelines/` (ver
  `Pasos/telemetria-pipeline-implementacion.md`).
- **`services/job_runner/` sin `__init__.py`, imports absolutos**: se siguió
  el patrón de `services/incidents-api/` (módulos flat) en vez del de
  `data/pipelines/exec_weekly_inventory_kpis/` (paquete con imports
  relativos), porque `job_runner` tiene la misma forma que `incidents-api`
  a nivel de módulo (varios `.py` planos en un directorio, sin subpaquetes
  propios) y así lo importan igual `scripts/nightly_export.py` y
  `scripts/seed_incidents.py`.

## Pendiente / siguientes pasos

1. Instalar la expresión cron de `infra/nightly_export.cron` en el servidor
   real (`crontab -e`) una vez exista un host fijo para correrla — hoy solo
   está documentada, no hay ningún crontab del sistema modificado desde este
   entorno.
2. Reactivar Supabase y correr `scripts/nightly_export.py` de punta a punta
   contra datos reales (hasta ahora solo SQLite + subproceso real de
   `pipeline.py`, que a su vez falla por falta de Supabase — comportamiento
   esperado, no un bug).
3. Si además de cron se quiere un disparador manual/HTTP de `nightly_export`
   (como ya existe para el pipeline de KPIs vía
   `POST /reporting/exec-weekly/run`), sería un cuarto endpoint en
   `services/reporting/` o un servicio propio — no pedido por esta guía, no
   implementado.
4. `services/job_runner/tests/` no corre en el mismo `pytest` que
   `data/pipelines/tests/` (venvs separados) — si se agrega CI, cada paquete
   necesita su propio paso (`cd services/job_runner && pytest`,
   `cd data/pipelines && pytest`).
