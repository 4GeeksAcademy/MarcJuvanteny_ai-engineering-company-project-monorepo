"""Constantes de `job_runs`. Sin secretos ni conexion (ver `db.py`)."""

from __future__ import annotations

# Esquema separado de `reporting` (que es del pipeline de KPIs, Hito 6):
# `job_runs` es control de scheduling general, no bookkeeping de un pipeline
# especifico -- no se fusiona con `reporting.pipeline_runs`.
JOB_RUNS_SCHEMA = "ops"
JOB_RUNS_TABLE = "job_runs"

# job_name del script scripts/nightly_export.py. Constante compartida para
# que el script y cualquier consumidor futuro (un endpoint de status, otro
# script) usen siempre el mismo literal.
NIGHTLY_EXPORT_JOB_NAME = "nightly_export"

VALID_STATUSES = {"pending", "processing", "completed", "failed"}
