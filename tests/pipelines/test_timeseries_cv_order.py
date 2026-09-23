"""Valida que la validación cruzada temporal de
`scripts/evaluate_sales_forecast.py` preserva el orden cronológico de los
datos en cada fold — CONTEXT5.md / guía "Evaluación de un Modelo de
Regresión", sección "Validación cruzada respetando el tiempo": *"ningún
índice de un fold posterior aparece antes que uno de un fold anterior"*.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import TimeSeriesSplit

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from evaluate_sales_forecast import N_SPLITS, time_series_cv  # noqa: E402


def test_time_series_split_never_shuffles_within_a_fold():
    """Cada fold: todo índice de train < todo índice de validación (ni
    train ni validación quedan barajados dentro del fold)."""
    X = np.arange(100).reshape(-1, 1)
    splitter = TimeSeriesSplit(n_splits=N_SPLITS)

    for train_idx, val_idx in splitter.split(X):
        assert train_idx.max() < val_idx.min()
        assert list(train_idx) == sorted(train_idx)
        assert list(val_idx) == sorted(val_idx)


def test_validation_windows_progress_forward_across_folds():
    """Ningún índice de un fold posterior aparece antes que uno de un fold
    anterior: la ventana de validación de cada fold empieza después de
    donde terminó la del fold previo."""
    X = np.arange(100).reshape(-1, 1)
    splitter = TimeSeriesSplit(n_splits=N_SPLITS)

    val_windows = [val_idx for _, val_idx in splitter.split(X)]
    assert len(val_windows) == N_SPLITS
    for earlier, later in zip(val_windows, val_windows[1:]):
        assert earlier.max() < later.min()


def test_production_time_series_cv_respects_chronological_order():
    """Ejercita `evaluate_sales_forecast.time_series_cv()` real (no solo
    `TimeSeriesSplit` aislado): esa función trae su propio `assert` de
    orden cronológico por fold -- si algún cambio futuro lo rompiera, este
    test fallaría acá, no en producción."""
    n_rows = 90
    rng = np.random.default_rng(0)
    month_num = (np.arange(n_rows) % 12) + 1
    trend = np.linspace(100_000, 200_000, n_rows)
    ratio = rng.normal(1.0, 0.1, n_rows)

    synthetic_train_features = pd.DataFrame(
        {
            "month": pd.date_range("2017-01-01", periods=n_rows, freq="MS"),
            "month_num": month_num,
            "month_sin": np.sin(2 * np.pi * month_num / 12),
            "month_cos": np.cos(2 * np.pi * month_num / 12),
            "lag_1": rng.normal(1.0, 0.1, n_rows),
            "lag_12": rng.normal(1.0, 0.1, n_rows),
            "rolling_mean_3": rng.normal(1.0, 0.1, n_rows),
            "rolling_std_3": rng.normal(0.1, 0.02, n_rows),
            "seasonal_ratio": ratio,
            "trend": trend,
            "revenue_eur": trend * ratio,
        }
    )

    summary = time_series_cv(synthetic_train_features)  # no debe disparar el assert interno

    assert len(summary["folds"]) == N_SPLITS
    for fold in summary["folds"]:
        assert fold["train_idx_max"] < fold["val_idx_min"]


def test_shuffled_input_still_yields_chronological_folds_because_split_uses_position():
    """`TimeSeriesSplit` particiona por *posición* en el array, no por una
    columna de fecha -- por eso `train_sales_forecast.prepare_train_test_features()`
    debe entregarle siempre un DataFrame ya ordenado cronológicamente. Este
    test documenta esa dependencia: si a `time_series_cv()` le llega un
    DataFrame con las filas barajadas, los folds ya NO representan una
    partición cronológica real, aunque `TimeSeriesSplit` no lo detecte."""
    n_rows = 90
    rng = np.random.default_rng(1)
    month_num = (np.arange(n_rows) % 12) + 1
    trend = np.linspace(100_000, 200_000, n_rows)
    ratio = rng.normal(1.0, 0.1, n_rows)
    months = pd.date_range("2017-01-01", periods=n_rows, freq="MS")

    ordered = pd.DataFrame(
        {
            "month": months,
            "month_num": month_num,
            "month_sin": np.sin(2 * np.pi * month_num / 12),
            "month_cos": np.cos(2 * np.pi * month_num / 12),
            "lag_1": rng.normal(1.0, 0.1, n_rows),
            "lag_12": rng.normal(1.0, 0.1, n_rows),
            "rolling_mean_3": rng.normal(1.0, 0.1, n_rows),
            "rolling_std_3": rng.normal(0.1, 0.02, n_rows),
            "seasonal_ratio": ratio,
            "trend": trend,
            "revenue_eur": trend * ratio,
        }
    )
    shuffled = ordered.sample(frac=1, random_state=2).reset_index(drop=True)

    # Con el orden correcto, los "meses" de cada fold de validacion son
    # estrictamente posteriores a los del fold de train de ese mismo fold.
    ordered_summary = time_series_cv(ordered)
    for fold_result, (_, val_idx) in zip(ordered_summary["folds"], TimeSeriesSplit(n_splits=N_SPLITS).split(ordered)):
        val_months = ordered["month"].iloc[val_idx]
        train_months = ordered["month"].iloc[: val_idx.min()]
        assert train_months.max() < val_months.min()

    # Con el DataFrame barajado, esa garantia temporal ya no existe -- el
    # "orden cronologico" que TimeSeriesSplit preserva es el de la POSICION
    # en el array, no el de la columna month.
    shuffled_summary = time_series_cv(shuffled)  # igual corre sin lanzar (posicionalmente sigue siendo valido)
    assert len(shuffled_summary["folds"]) == N_SPLITS
    any_fold_month_order_violated = False
    for _, val_idx in TimeSeriesSplit(n_splits=N_SPLITS).split(shuffled):
        val_months = shuffled["month"].iloc[val_idx]
        train_months = shuffled["month"].iloc[: val_idx.min()]
        if train_months.max() >= val_months.min():
            any_fold_month_order_violated = True
    assert any_fold_month_order_violated, (
        "se esperaba que barajar el DataFrame rompiera el orden cronologico real "
        "(por columna 'month'), aunque TimeSeriesSplit no lo note (particiona por posicion)"
    )
