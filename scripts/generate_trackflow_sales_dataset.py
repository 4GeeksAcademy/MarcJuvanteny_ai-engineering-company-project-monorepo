"""Genera `data/raw/trackflow_sales.csv`.

`CONTEXT/CONTEXT5.md` (secciones 2 y 4) describe este archivo como "ya
incluido en tu monorepo", determinista (`random_state=42`), pero el archivo
no existe en este repo.

**Historial de esta entrega**: la primera versión de este script *sintetizaba*
la serie `consolidated` desde cero (crecimiento 6%±3%, estacionalidad
Nov-Dic/Feb) porque no había ningún dato real disponible en el repo — ver
`Pasos/sales-forecast-model.md`. Con la guía de evaluación
(`CONTEXT/CONTEXT5.md`) llegó `CONTEXT/sales.md`: el CSV real de
`revenue_eur`/`shipments_processed`/`avg_revenue_per_shipment_eur` por mes
(120 filas `consolidated`, 2016-01 a 2025-12). Esta versión usa esos datos
reales tal cual — ya no se sintetiza `revenue_eur` — y solo genera de forma
sintética el split `us`/`spain` (Sección 5 del CONTEXT5 explícitamente lo
permite: *"El dataset provisto solo incluye la fila consolidated; si separas
por mercado como feature adicional... usa aproximadamente 60/40"*), porque
esa columna no viene en `sales.md`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT_DIR / "CONTEXT" / "sales.md"
OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "trackflow_sales.csv"

RANDOM_STATE = 42


def load_real_consolidated_rows(source_path: Path = SOURCE_PATH) -> pd.DataFrame:
    """`CONTEXT/sales.md` es CSV real (no markdown): mismo header/columnas
    que `data/raw/trackflow_sales.csv`, solo con la fila `consolidated`."""
    df = pd.read_csv(source_path, parse_dates=["month"])
    if not (df["market"] == "consolidated").all():
        raise ValueError(f"{source_path} deberia traer solo filas 'consolidated'.")
    return df.sort_values("month").reset_index(drop=True)


def split_by_market(consolidated: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Genera las filas `us`/`spain` a partir de `consolidated`, ~60/40 (Sección 5 del CONTEXT5)."""
    market_rows: list[dict[str, object]] = []

    for _, row in consolidated.iterrows():
        us_share = float(np.clip(rng.normal(0.60, 0.02), 0.55, 0.65))
        shares = {"us": us_share, "spain": 1 - us_share}

        for market, share in shares.items():
            revenue = round(row["revenue_eur"] * share, 2)
            shipments = max(1, round(row["shipments_processed"] * share))
            market_rows.append(
                {
                    "month": row["month"],
                    "revenue_eur": revenue,
                    "shipments_processed": int(shipments),
                    "avg_revenue_per_shipment_eur": round(revenue / shipments, 4),
                    "market": market,
                }
            )

    return pd.DataFrame(market_rows)


def main() -> None:
    rng = np.random.default_rng(RANDOM_STATE)

    consolidated = load_real_consolidated_rows()
    by_market = split_by_market(consolidated, rng)

    full = pd.concat([consolidated, by_market], ignore_index=True)
    full = full.sort_values(["month", "market"]).reset_index(drop=True)
    full["month"] = full["month"].dt.strftime("%Y-%m-%d")

    assert (full["revenue_eur"] > 0).all(), "revenue_eur debe ser siempre positivo (Seccion 5 del CONTEXT5)"
    assert len(consolidated) == 120, "deben ser 120 filas consolidated (10 anios x 12 meses)"
    assert consolidated["month"].dt.to_period("M").drop_duplicates().shape[0] == 120, "no debe haber meses faltantes"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    full.to_csv(OUTPUT_PATH, index=False)
    print(f"Generadas {len(full)} filas ({len(consolidated)} consolidated, reales) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
