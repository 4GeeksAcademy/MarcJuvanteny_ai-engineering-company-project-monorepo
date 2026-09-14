"""Genera `data/raw/trackflow_sales.csv`.

`CONTEXT/CONTEXTPredicción.md` (sección 2 y 4) describe este archivo como
"ya incluido en tu monorepo" con un patrón determinista (`random_state=42`),
pero el archivo no existe en este repo. Este script lo genera desde cero
siguiendo **exactamente** las reglas documentadas en esa sección:

- 10 años mensuales, 2016-01 a 2025-12 (120 meses `consolidated`, sin huecos).
- Crecimiento anual base `X=6%`, variación `Y=3%`: el crecimiento real de
  cada año alterna entre `X+Y=9%` y `X-Y=3%` (empezando por `X+Y` en 2017;
  2016 es el año base, sin crecimiento aplicado sobre sí mismo).
- Estacionalidad: Nov-Dic +25-35% sobre la tendencia del año: Feb -10-15%;
  el resto de los meses fluctúa +-5% alrededor de la tendencia del año.
- Split aproximado 60/40 entre mercado `us` y `spain`.
- Todo `revenue_eur` > 0; ningun mes faltante.

Lo único que la sección 2/4 del CONTEXT **no** especifica es el punto de
partida absoluto (ingreso mensual de enero de 2016) ni el ingreso promedio
por envío -- son elecciones de este generador, documentadas abajo
(`BASE_MONTHLY_REVENUE_EUR_2016`, `BASE_AVG_REVENUE_PER_SHIPMENT_EUR`), no
datos provistos por el CONTEXT.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "trackflow_sales.csv"

RANDOM_STATE = 42
START_YEAR = 2016
END_YEAR = 2025  # inclusive

# Elecciones propias del generador (no provistas por el CONTEXT, ver docstring):
BASE_MONTHLY_REVENUE_EUR_2016 = 250_000.0  # ingreso mensual medio de referencia, año base
BASE_AVG_REVENUE_PER_SHIPMENT_EUR = 20.0  # ingreso medio por envio, punto de partida

X = 0.06  # crecimiento anual base
Y = 0.03  # variacion del crecimiento anual

HIGH_SEASON_MONTHS = {11, 12}  # noviembre, diciembre
LOW_SEASON_MONTH = 2  # febrero


def _annual_growth_rate(year: int) -> float:
    """`d` para `year` (crecimiento vs. el año anterior). 2016 es el año base: 0."""
    if year == START_YEAR:
        return 0.0
    # Alterna empezando por X+Y en el primer año posterior al base (2017).
    return (X + Y) if (year - START_YEAR) % 2 == 1 else (X - Y)


def _annual_avg_monthly_revenue() -> dict[int, float]:
    """Ingreso mensual medio "de tendencia" por año (antes de estacionalidad)."""
    levels: dict[int, float] = {}
    level = BASE_MONTHLY_REVENUE_EUR_2016
    for year in range(START_YEAR, END_YEAR + 1):
        level = level * (1 + _annual_growth_rate(year)) if year != START_YEAR else level
        levels[year] = level
    return levels


def generate_consolidated_rows(rng: np.random.Generator) -> pd.DataFrame:
    annual_avg = _annual_avg_monthly_revenue()
    rows: list[dict[str, object]] = []

    # Segunda serie independiente para el volumen de envios: mismo patron de
    # tendencia/estacionalidad de negocio (mas envios en Nov-Dic, menos en
    # Feb), pero con su propio ruido -- para que avg_revenue_per_shipment_eur
    # (= revenue_eur / shipments_processed) varie de forma realista mes a
    # mes en vez de quedar fijo.
    base_shipments_2016 = BASE_MONTHLY_REVENUE_EUR_2016 / BASE_AVG_REVENUE_PER_SHIPMENT_EUR
    shipments_level = {}
    level = base_shipments_2016
    for year in range(START_YEAR, END_YEAR + 1):
        level = level * (1 + _annual_growth_rate(year)) if year != START_YEAR else level
        shipments_level[year] = level

    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            if month in HIGH_SEASON_MONTHS:
                seasonal_factor_revenue = 1 + rng.uniform(0.25, 0.35)
                seasonal_factor_shipments = 1 + rng.uniform(0.25, 0.35)
            elif month == LOW_SEASON_MONTH:
                seasonal_factor_revenue = 1 - rng.uniform(0.10, 0.15)
                seasonal_factor_shipments = 1 - rng.uniform(0.10, 0.15)
            else:
                seasonal_factor_revenue = 1 + rng.uniform(-0.05, 0.05)
                seasonal_factor_shipments = 1 + rng.uniform(-0.05, 0.05)

            revenue = annual_avg[year] * seasonal_factor_revenue
            shipments = max(1, round(shipments_level[year] * seasonal_factor_shipments))

            rows.append(
                {
                    "month": pd.Timestamp(year=year, month=month, day=1),
                    "revenue_eur": round(revenue, 2),
                    "shipments_processed": int(shipments),
                    "avg_revenue_per_shipment_eur": round(revenue / shipments, 4),
                    "market": "consolidated",
                }
            )

    return pd.DataFrame(rows)


def split_by_market(consolidated: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Genera las filas `us`/`spain` a partir de `consolidated`, ~60/40 (Sección 5 del CONTEXT)."""
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

    consolidated = generate_consolidated_rows(rng)
    by_market = split_by_market(consolidated, rng)

    full = pd.concat([consolidated, by_market], ignore_index=True)
    full = full.sort_values(["month", "market"]).reset_index(drop=True)
    full["month"] = full["month"].dt.strftime("%Y-%m-%d")

    assert (full["revenue_eur"] > 0).all(), "revenue_eur debe ser siempre positivo (Seccion 5 del CONTEXT)"
    assert len(consolidated) == 120, "deben ser 120 filas consolidated (10 anios x 12 meses)"
    assert consolidated["month"].dt.to_period("M").drop_duplicates().shape[0] == 120, "no debe haber meses faltantes"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    full.to_csv(OUTPUT_PATH, index=False)
    print(f"Generadas {len(full)} filas ({len(consolidated)} consolidated) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
