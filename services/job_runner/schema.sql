-- DDL Postgres de referencia para `ops.job_runs` (ver schema.py para la
-- version SQLAlchemy Core, portable, usada por ensure_schema()).
-- Deploy manual: psql "$SUPABASE_DATABASE_URL" -f services/job_runner/schema.sql

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.job_runs (
    id            TEXT PRIMARY KEY,
    job_name      TEXT NOT NULL,
    target_date   DATE NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotencia por dia: "ya existe una corrida completed para
-- (job_name, target_date)?" (has_completed_for_date() en runner.py).
CREATE INDEX IF NOT EXISTS ix_job_runs_job_name_target_date
    ON ops.job_runs (job_name, target_date);

-- Lock: a lo sumo una fila "processing" por job_name a la vez. Sin tabla ni
-- columna de lock aparte -- es el propio job_runs con un indice unico
-- parcial. Un INSERT concurrente con la misma condicion viola esta
-- constraint (ver JobLockHeldError en runner.py).
CREATE UNIQUE INDEX IF NOT EXISTS ux_job_runs_processing_lock
    ON ops.job_runs (job_name) WHERE status = 'processing';
