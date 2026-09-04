"""Tests de `scripts/nightly_export.py` contra SQLite en memoria.

`export_telemetry_csv`/`run_pipeline_subprocess` se monkeypatchean (I/O real
de archivo + subproceso real ya se ejercitan en un smoke test manual, no
comiteado, contra `data/pipelines/pipeline.py` de verdad -- ver
`Pasos/telemetria-nightly-export-job-runner.md`); estos tests se concentran
en la maquina de estados de `main()` sobre `job_runs`: lock, idempotencia por
`target_date`, y la invariante "ningun registro queda en 'processing' tras
una ejecucion fallida" (incluyendo un `KeyboardInterrupt`, no solo `Exception`).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.path.insert(0, str(ROOT_DIR / "services" / "job_runner"))

import nightly_export  # noqa: E402
import runner as job_runner  # noqa: E402

JOB_NAME = "nightly_export"
TARGET_DATE = date(2026, 9, 3)


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    job_runner.ensure_schema(engine, schema="")
    return engine


@pytest.fixture(autouse=True)
def patched_env(monkeypatch, engine):
    """Fuerza schema="" (SQLite) en cada funcion de job_runner que usa main(),
    igual que force_empty_schema en data/pipelines/tests/test_flow.py.

    `nightly_export.job_runner` es literalmente el mismo objeto modulo que
    `job_runner` aqui (Python cachea `runner.py` una sola vez en
    sys.modules), asi que hay que capturar las funciones originales *antes*
    de reemplazarlas -- si el reemplazo llama a `job_runner.ensure_schema`
    por nombre, para entonces ya se esta llamando a si mismo (recursion
    infinita).
    """
    original = {name: getattr(job_runner, name) for name in ["ensure_schema", "has_processing_lock", "has_completed_for_date", "start_job_run", "mark_completed", "mark_failed"]}

    monkeypatch.setattr(nightly_export, "job_runner_db", type("_M", (), {"get_engine": staticmethod(lambda: engine)}))
    monkeypatch.setattr(nightly_export.job_runner, "ensure_schema", lambda e, schema="ops": original["ensure_schema"](e, schema=""))
    monkeypatch.setattr(
        nightly_export.job_runner, "has_processing_lock", lambda e, job_name, schema="ops": original["has_processing_lock"](e, job_name, schema="")
    )
    monkeypatch.setattr(
        nightly_export.job_runner,
        "has_completed_for_date",
        lambda e, job_name, td, schema="ops": original["has_completed_for_date"](e, job_name, td, schema=""),
    )
    monkeypatch.setattr(
        nightly_export.job_runner, "start_job_run", lambda e, job_name, td, schema="ops": original["start_job_run"](e, job_name, td, schema="")
    )
    monkeypatch.setattr(
        nightly_export.job_runner, "mark_completed", lambda e, run_id, schema="ops": original["mark_completed"](e, run_id, schema="")
    )
    monkeypatch.setattr(
        nightly_export.job_runner, "mark_failed", lambda e, run_id, msg, schema="ops": original["mark_failed"](e, run_id, msg, schema="")
    )
    monkeypatch.setenv("TARGET_DATE", TARGET_DATE.isoformat())


def _latest(engine):
    return job_runner.get_latest_job_run(engine, JOB_NAME, schema="")


def test_lock_cancels_without_touching_the_processing_row(engine, monkeypatch):
    existing_run_id = job_runner.start_job_run(engine, JOB_NAME, TARGET_DATE, schema="")

    nightly_export.main()

    latest = _latest(engine)
    assert latest["id"] == existing_run_id
    assert latest["status"] == "processing"  # main() no la toco


def test_completed_for_date_skips_export_and_pipeline(engine, monkeypatch):
    run_id = job_runner.start_job_run(engine, JOB_NAME, TARGET_DATE, schema="")
    job_runner.mark_completed(engine, run_id, schema="")

    called = {"export": False, "pipeline": False}
    monkeypatch.setattr(nightly_export, "export_telemetry_csv", lambda td: called.__setitem__("export", True))
    monkeypatch.setattr(nightly_export, "run_pipeline_subprocess", lambda td: called.__setitem__("pipeline", True))

    nightly_export.main()

    assert called == {"export": False, "pipeline": False}


def test_pipeline_failure_marks_failed_not_left_processing(engine, monkeypatch):
    monkeypatch.setattr(nightly_export, "export_telemetry_csv", lambda td: None)

    def _boom(td):
        raise RuntimeError("pipeline.py fallo (exit 1): boom")

    monkeypatch.setattr(nightly_export, "run_pipeline_subprocess", _boom)

    with pytest.raises(RuntimeError):
        nightly_export.main()

    latest = _latest(engine)
    assert latest["status"] == "failed"  # nunca queda "processing"
    assert "boom" in latest["error_message"]


def test_keyboard_interrupt_also_marks_failed_not_left_processing(engine, monkeypatch):
    """BaseException, no solo Exception: un Ctrl+C/SIGTERM tampoco puede dejar
    la fila colgada en 'processing' (ver el comentario en main())."""
    monkeypatch.setattr(nightly_export, "export_telemetry_csv", lambda td: None)

    def _interrupt(td):
        raise KeyboardInterrupt()

    monkeypatch.setattr(nightly_export, "run_pipeline_subprocess", _interrupt)

    with pytest.raises(KeyboardInterrupt):
        nightly_export.main()

    latest = _latest(engine)
    assert latest["status"] == "failed"


def test_success_marks_completed(engine, monkeypatch):
    monkeypatch.setattr(nightly_export, "export_telemetry_csv", lambda td: None)
    monkeypatch.setattr(nightly_export, "run_pipeline_subprocess", lambda td: None)

    nightly_export.main()

    latest = _latest(engine)
    assert latest["status"] == "completed"
