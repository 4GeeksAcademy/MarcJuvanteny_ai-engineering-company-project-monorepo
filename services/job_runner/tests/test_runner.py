"""Tests de `runner.py` contra SQLite en memoria (mismo motivo que
data/pipelines/tests/: Supabase esta pausado en este entorno). Ejercita el
mismo codigo de schema.py/runner.py que corre contra Postgres, solo con
schema="" porque SQLite no soporta `esquema.tabla` como Postgres.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import runner as job_runner  # noqa: E402


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    job_runner.ensure_schema(engine, schema="")
    return engine


def test_has_processing_lock_and_has_completed_for_date_start_false(engine):
    assert job_runner.has_processing_lock(engine, "nightly_export", schema="") is False
    assert job_runner.has_completed_for_date(engine, "nightly_export", date(2026, 9, 3), schema="") is False


def test_start_job_run_sets_processing_and_lock_blocks_a_second_start(engine):
    run_id = job_runner.start_job_run(engine, "nightly_export", date(2026, 9, 3), schema="")
    assert job_runner.has_processing_lock(engine, "nightly_export", schema="") is True

    # El indice unico parcial (ux_job_runs_processing_lock) es lo que
    # realmente bloquea esto, no solo has_processing_lock(): mismo job_name,
    # otro target_date, igual debe fallar mientras la primera siga
    # "processing".
    with pytest.raises(job_runner.JobLockHeldError):
        job_runner.start_job_run(engine, "nightly_export", date(2026, 9, 4), schema="")

    latest = job_runner.get_latest_job_run(engine, "nightly_export", schema="")
    assert latest["id"] == run_id
    assert latest["status"] == "processing"


def test_mark_completed_releases_lock_and_sets_idempotency_flag(engine):
    run_id = job_runner.start_job_run(engine, "nightly_export", date(2026, 9, 3), schema="")
    job_runner.mark_completed(engine, run_id, schema="")

    assert job_runner.has_processing_lock(engine, "nightly_export", schema="") is False
    assert job_runner.has_completed_for_date(engine, "nightly_export", date(2026, 9, 3), schema="") is True
    # Un job_name sin ese target_date exacto no cuenta como completado (la
    # clave de idempotencia es el par, no solo job_name).
    assert job_runner.has_completed_for_date(engine, "nightly_export", date(2026, 9, 4), schema="") is False

    # El lock ya se libero: otra corrida (otro dia) puede arrancar.
    second_run_id = job_runner.start_job_run(engine, "nightly_export", date(2026, 9, 4), schema="")
    assert second_run_id != run_id


def test_mark_failed_records_error_message_and_releases_lock(engine):
    run_id = job_runner.start_job_run(engine, "nightly_export", date(2026, 9, 3), schema="")
    job_runner.mark_failed(engine, run_id, "boom", schema="")

    latest = job_runner.get_latest_job_run(engine, "nightly_export", schema="")
    assert latest["status"] == "failed"
    assert latest["error_message"] == "boom"
    assert job_runner.has_processing_lock(engine, "nightly_export", schema="") is False
    assert job_runner.has_completed_for_date(engine, "nightly_export", date(2026, 9, 3), schema="") is False


def test_different_job_names_do_not_share_the_lock(engine):
    job_runner.start_job_run(engine, "nightly_export", date(2026, 9, 3), schema="")
    # Un job_name distinto no esta bloqueado por el lock de "nightly_export".
    other_run_id = job_runner.start_job_run(engine, "another_job", date(2026, 9, 3), schema="")
    assert other_run_id is not None
    assert job_runner.has_processing_lock(engine, "another_job", schema="") is True
