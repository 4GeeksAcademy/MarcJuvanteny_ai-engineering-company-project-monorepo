"""Hace importable `exec_weekly_inventory_kpis` (vive en data/pipelines/, fuera
de este servicio) sin duplicar su codigo aqui.

`services/reporting/` es una capa HTTP fina (Fase 5.1 del diseno): no conoce
detalles de extraccion/transformacion/carga, solo llama a `flow.py` y
`queries.py`. Se importa por su efecto secundario antes de cualquier
`from exec_weekly_inventory_kpis import ...`:

    import pipeline_path  # noqa: F401
    from exec_weekly_inventory_kpis import queries
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
PIPELINES_DIR = SERVICE_DIR.parent.parent / "data" / "pipelines"

if not PIPELINES_DIR.is_dir():
    raise RuntimeError(f"No se encontro data/pipelines/ en {PIPELINES_DIR}")

if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))
