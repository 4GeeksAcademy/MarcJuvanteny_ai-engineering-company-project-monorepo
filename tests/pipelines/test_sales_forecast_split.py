"""Valida el split de `scripts/train_sales_forecast.py` contra la regla del
CONTEXT (`CONTEXT/CONTEXTPredicción.md`, sección 6): primeros 8 años ->
entrenamiento, 2 años más recientes -> prueba, sin fuga de datos entre
ambos conjuntos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from train_sales_forecast import DEFAULT_CSV_PATH, load_consolidated_sales, split_train_test  # noqa: E402


def _synthetic_consolidated(years: list[int]) -> pd.DataFrame:
    """12 filas `consolidated` por año, sin depender del CSV real generado."""
    rows = []
    for year in years:
        for month in range(1, 13):
            rows.append(
                {
                    "month": pd.Timestamp(year=year, month=month, day=1),
                    "revenue_eur": 100_000.0 + year + month,
                    "shipments_processed": 5000,
                    "avg_revenue_per_shipment_eur": 20.0,
                    "market": "consolidated",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_10_years() -> pd.DataFrame:
    return _synthetic_consolidated(list(range(2016, 2026)))  # 2016..2025, 10 anios


def test_split_covers_exactly_8_and_2_years(synthetic_10_years):
    train_df, test_df = split_train_test(synthetic_10_years, train_years=8)

    assert sorted(train_df["month"].dt.year.unique()) == list(range(2016, 2024))  # 8 anios
    assert sorted(test_df["month"].dt.year.unique()) == [2024, 2025]  # 2 anios
    assert len(train_df) == 8 * 12  # 96 filas
    assert len(test_df) == 2 * 12  # 24 filas
    assert len(train_df) + len(test_df) == len(synthetic_10_years)  # no se pierde ni se duplica ninguna fila


def test_no_month_overlap_between_train_and_test(synthetic_10_years):
    train_df, test_df = split_train_test(synthetic_10_years, train_years=8)

    train_months = set(train_df["month"])
    test_months = set(test_df["month"])
    assert train_months.isdisjoint(test_months)


def test_split_is_strictly_chronological_no_leakage(synthetic_10_years):
    """El modelo nunca debe ver un mes de prueba antes de terminar de ver
    entrenamiento: todo el rango de train debe preceder a todo el rango de
    test. Esto es lo que hace estructuralmente imposible la fuga de datos
    (no solo "no se solapan", sino "test es siempre posterior")."""
    train_df, test_df = split_train_test(synthetic_10_years, train_years=8)

    assert train_df["month"].max() < test_df["month"].min()


def test_split_does_not_depend_on_input_row_order(synthetic_10_years):
    """Barajar las filas de entrada no debe cambiar el resultado del split
    (si el split dependiera implicitamente del orden de las filas en vez de
    la columna `month`, esto lo detectaria)."""
    shuffled = synthetic_10_years.sample(frac=1, random_state=7).reset_index(drop=True)

    train_a, test_a = split_train_test(synthetic_10_years, train_years=8)
    train_b, test_b = split_train_test(shuffled, train_years=8)

    assert set(train_a["month"]) == set(train_b["month"])
    assert set(test_a["month"]) == set(test_b["month"])


def test_real_generated_dataset_also_respects_the_8_2_year_split():
    """Integracion liviana contra data/raw/trackflow_sales.csv real (generado
    por scripts/generate_trackflow_sales_dataset.py) -- no solo datos sinteticos."""
    if not DEFAULT_CSV_PATH.exists():
        pytest.skip(f"{DEFAULT_CSV_PATH} no existe; correr scripts/generate_trackflow_sales_dataset.py primero.")

    consolidated = load_consolidated_sales(DEFAULT_CSV_PATH)
    train_df, test_df = split_train_test(consolidated)

    assert sorted(train_df["month"].dt.year.unique()) == list(range(2016, 2024))
    assert sorted(test_df["month"].dt.year.unique()) == [2024, 2025]
    assert train_df["month"].max() < test_df["month"].min()
    assert set(train_df["month"]).isdisjoint(set(test_df["month"]))
