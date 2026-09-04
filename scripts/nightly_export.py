"""Exportacion nocturna de telemetria + disparo del pipeline de KPIs.

Pensado para correr una vez por noche via cron (ver `infra/nightly_export.cron`
para la expresion exacta y por que se eligio ese horario). Cada corrida:

  1. Resuelve `target_date`: env `TARGET_DATE` (`YYYY-MM-DD`) o, por defecto,
     ayer en UTC.
  2. Aborta (silenciosamente, sin marcar error) si ya hay una corrida
     `processing` de `nightly_export` en `ops.job_runs` -- lock, ver
     `services/job_runner/runner.py`.
  3. Aborta si ya existe una corrida `completed` para
     `(job_name="nightly_export", target_date)` -- idempotencia por dia.
  4. Exporta las filas de `telemetry_events` del dia a
     `data/raw/telemetry_<target_date>.csv` (snapshot de backup/auditoria; el
     pipeline en si lee de la base, nunca de este CSV). Solo si el archivo no
     existe todavia.
  5. Lanza `data/pipelines/pipeline.py` como subproceso -- el entry point CLI
     del pipeline de KPIs (Hito 6), en vez del `telemetry_kpi_daily.run`
     generico de la guia: ese pipeline es semanal (ISO week), no diario, asi
     que se le pasa la semana ISO que contiene `target_date`. Correrlo cada
     noche mantiene "al dia" la semana en curso sin duplicar nada (UPSERT
     idempotente por clave natural, Fase 3 del pipeline).
  6. Registra el resultado final (`completed`/`failed` + error) en
     `ops.job_runs` (`services/job_runner/`).

`ops.job_runs` es control de scheduling general, deliberadamente separado de
`reporting.pipeline_runs` (que es bookkeeping de una corrida del pipeline en
si, Hito 6) -- ver la nota de arquitectura en
`Pasos/telemetria-nightly-export-job-runner.md`.

**Disparador**: este script se dispara por **cron del SO**
(`infra/nightly_export.cron`), nunca desde dentro del proceso de una API.
Deliberadamente no hay `APScheduler`, `@repeat_every` ni un hook `lifespan`
en `services/incidents-api/main.py` o `services/reporting/main.py` que lo
invoquen: correrlo en el mismo proceso/hilo que sirve requests HTTP
arriesgaria bloquear ese hilo durante el subproceso del pipeline (potencialmente
minutos) y acoplaria el ciclo de vida de un job nocturno al de un servidor
que debe seguir respondiendo. Si en el futuro se reemplaza cron por un
contenedor scheduler dedicado (systemd timer, un cronjob de k8s, Prefect
deployment, etc.), sigue siendo un **worker separado** que invoca este mismo
`main()` -- nunca el proceso de la API.

Ejecucion: `python scripts/nightly_export.py`, con las dependencias de
`services/job_runner/requirements.txt` instaladas en el interprete que lo
corre (sqlalchemy, psycopg2-binary, python-dotenv, pandas). Variable de
entorno opcional `TARGET_DATE` (`YYYY-MM-DD`) para fijar la fecha objetivo en
pruebas/backfills manuales sin tocar código -- ver `resolve_target_date()`.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
JOB_RUNNER_DIR = ROOT_DIR / "services" / "job_runner"
if str(JOB_RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(JOB_RUNNER_DIR))

import config as job_runner_config  # noqa: E402
import db as job_runner_db  # noqa: E402
import runner as job_runner  # noqa: E402
from runner import JobLockHeldError  # noqa: E402

JOB_NAME = job_runner_config.NIGHTLY_EXPORT_JOB_NAME
RAW_DIR = ROOT_DIR / "data" / "raw"
PIPELINE_SCRIPT = ROOT_DIR / "data" / "pipelines" / "pipeline.py"
# data/pipelines/ tiene su propio venv (deps: prefect, pandas, sqlalchemy,
# psycopg2-binary) -- mismo motivo que services/reporting/Dockerfile: cada
# servicio/paquete del monorepo gestiona su propio entorno. Si no existe (p.
# ej. CI sin setup previo), cae al interprete que corre este script.
PIPELINE_VENV_PYTHON = ROOT_DIR / "data" / "pipelines" / ".venv" / "bin" / "python"


# --- Observabilidad -----------------------------------------------------
# INFO para eventos normales (inicio, fin, omision por duplicado/lock);
# ERROR para excepciones. Cada linea lleva timestamp (%(asctime)s), el
# nombre del job y el estado resultante como campos estructurados (no solo
# texto libre), para poder grepear "status=failed" en el log sin parsear
# frases. cron redirige stdout (ver infra/nightly_export.cron) a un archivo,
# asi que un StreamHandler a stdout es "el log".
_LOG_FORMAT = "%(asctime)s %(levelname)s job=%(job)s status=%(status)s - %(message)s"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("nightly_export")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # no duplicar en el root logger
    return logger


_logger = _build_logger()


def _log_info(status: str, message: str, *args: object) -> None:
    _logger.info(message, *args, extra={"job": JOB_NAME, "status": status})


def _log_error(status: str, message: str, *args: object) -> None:
    _logger.error(message, *args, extra={"job": JOB_NAME, "status": status})


def resolve_target_date() -> date:
    raw_value = os.environ.get("TARGET_DATE")
    if raw_value:
        return date.fromisoformat(raw_value)
    return (datetime.now(timezone.utc) - timedelta(days=1)).date()


def export_telemetry_csv(target_date: date) -> Path:
    """`telemetry_events` del dia -> `data/raw/telemetry_<target_date>.csv`.

    Snapshot de backup/auditoria, no un input del pipeline (que sigue leyendo
    de la base). Si el archivo ya existe (re-run tras un crash a mitad de
    corrida, por ejemplo) no se vuelve a exportar.
    """
    csv_path = RAW_DIR / f"telemetry_{target_date.isoformat()}.csv"
    if csv_path.exists():
        _log_info("csv_exists", "%s ya existe, no se vuelve a exportar.", csv_path)
        return csv_path

    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    engine = job_runner_db.get_engine()
    query = text(
        "SELECT * FROM telemetry_events WHERE timestamp >= :day_start AND timestamp < :day_end ORDER BY timestamp"
    )
    with engine.connect() as connection:
        events_df = pd.read_sql(query, connection, params={"day_start": day_start, "day_end": day_end})

    if "properties" in events_df.columns and not events_df.empty:
        # En Postgres/JSONB, psycopg2 ya deserializa `properties` a dict; hay
        # que volver a serializarlo para que el CSV sea texto plano valido.
        events_df = events_df.copy()
        events_df["properties"] = events_df["properties"].apply(
            lambda value: value if isinstance(value, str) else json.dumps(value)
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    events_df.to_csv(csv_path, index=False)
    _log_info("csv_exported", "%d eventos exportados a %s.", len(events_df), csv_path)
    return csv_path


def iso_week_for(target_date: date) -> str:
    iso = target_date.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run_pipeline_subprocess(target_date: date) -> None:
    python_exe = str(PIPELINE_VENV_PYTHON) if PIPELINE_VENV_PYTHON.exists() else sys.executable
    iso_week = iso_week_for(target_date)
    command = [python_exe, str(PIPELINE_SCRIPT), "--iso-week", iso_week, "--trigger", "scheduled"]
    _log_info("pipeline_launch", "Lanzando pipeline: %s", " ".join(command))

    result = subprocess.run(command, capture_output=True, text=True)
    if result.stdout:
        _log_info("pipeline_output", "%s", result.stdout.rstrip())
    if result.returncode != 0:
        raise RuntimeError(f"pipeline.py fallo (exit {result.returncode}): {result.stderr[-2000:]}")


def main() -> None:
    target_date = resolve_target_date()
    _log_info("started", "Job iniciado para target_date=%s.", target_date)

    engine = job_runner_db.get_engine()
    job_runner.ensure_schema(engine)

    if job_runner.has_processing_lock(engine, JOB_NAME):
        _log_info("skipped_lock", "Ya hay una corrida 'processing' para '%s'; cancelado.", JOB_NAME)
        return

    if job_runner.has_completed_for_date(engine, JOB_NAME, target_date):
        _log_info("skipped_duplicate", "Ya hay una corrida 'completed' para %s/%s; cancelado.", JOB_NAME, target_date)
        return

    try:
        run_id = job_runner.start_job_run(engine, JOB_NAME, target_date)
    except JobLockHeldError as exc:
        # Otra corrida gano la carrera entre el chequeo de arriba y este
        # INSERT (la constraint de schema.py es lo que realmente lo
        # garantiza). Mismo desenlace que el chequeo previo: cancelar sin
        # marcar failed, esto no es un error del job.
        _log_info("skipped_lock", "%s Cancelado.", exc)
        return

    try:
        export_telemetry_csv(target_date)
        run_pipeline_subprocess(target_date)
    except BaseException as exc:
        # BaseException, no Exception: la invariante es "ningun registro
        # puede quedar en 'processing' tras una ejecucion fallida", y eso
        # incluye un KeyboardInterrupt/SystemExit (Ctrl+C, timeout externo
        # matando el proceso con SIGTERM->KeyboardInterrupt), que Exception
        # no captura. mark_failed() siempre corre antes de propagar.
        job_runner.mark_failed(engine, run_id, str(exc))
        _log_error("failed", "%s", exc)
        # El `raise` (sin exc_info en el log, para no duplicar la traceback)
        # hace que el proceso termine con exit != 0; cron redirige tambien
        # stderr (ver infra/nightly_export.cron), asi que la traceback
        # completa queda igual en el mismo log.
        raise
    else:
        job_runner.mark_completed(engine, run_id)
        _log_info("completed", "%s/%s terminado (run_id=%s).", JOB_NAME, target_date, run_id)


if __name__ == "__main__":
    main()
