"""Paso opcional / no critico del flow: snapshot de validacion en data/eval/.

No es parte del contrato de negocio (la tabla `reporting.exec_weekly_inventory_kpis`
ya es la fuente de verdad) y no debe interrumpir la corrida si falla: flow.py
lo invoca con `return_state=True` y solo registra un warning si peta.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import EVAL_SNAPSHOT_SUBDIR

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_EVAL_DIR = PACKAGE_DIR.parent.parent / "eval" / EVAL_SNAPSHOT_SUBDIR


def export_eval_snapshot(
    kpis_df: pd.DataFrame,
    run_id: str,
    iso_week: str,
    qc: dict[str, Any],
    eval_dir: Path = DEFAULT_EVAL_DIR,
) -> Path:
    """Vuelca el resultado de la corrida (KPIs + contadores de calidad) a data/eval/.

    Un archivo por corrida (`<iso_week>_<run_id>.json`), pensado para revision
    manual o para un futuro `data/eval/` de comparacion semana a semana, nunca
    para servir el dashboard (eso lo hace `queries.query_weekly_kpis`).
    """
    eval_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = eval_dir / f"{iso_week}_{run_id}.json"
    payload = {
        "run_id": run_id,
        "iso_week": iso_week,
        "quality_counters": qc,
        "kpis": kpis_df.to_dict(orient="records"),
    }
    snapshot_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return snapshot_path
