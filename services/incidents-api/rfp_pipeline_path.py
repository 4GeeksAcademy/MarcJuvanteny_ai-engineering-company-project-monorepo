"""Hace importable `rfp_intake` (vive en data/pipelines/, fuera de este
servicio) sin duplicar su codigo aqui. Mismo patron que
`services/knowledge-api/pipeline_path.py` para `data/pipelines/rag.py`.

    import rfp_pipeline_path  # noqa: F401
    from rfp_intake.pipeline import process_rfp_ticket
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
