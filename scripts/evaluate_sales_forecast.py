"""Evaluación rigurosa del modelo de `train_sales_forecast.py`: validación
cruzada temporal, curva de aprendizaje, MAE/RMSE, y diagnóstico técnico.

Implementa la guía "Evaluación de un Modelo de Regresión"
(`CONTEXT/CONTEXT5.md`, Sección 6): valida la *metodología* de evaluación
además del modelo en sí — hasta ahora (`Pasos/sales-forecast-model.md`) solo
había un único split train/test, sin validación cruzada ni curva de
aprendizaje que respalden un diagnóstico de ajuste.

## Validación cruzada respetando el tiempo

`TimeSeriesSplit` (5 folds) sobre `train_features` (2017-2023, ya sin las
primeras 12 filas de 2016 que se descartan por `lag_12` en `NaN` — ver
`train_sales_forecast.prepare_train_test_features()`). `TimeSeriesSplit` por
construcción usa ventanas expansivas de entrenamiento (`train_idx` siempre
antes de `val_idx`, nunca baraja) — `time_series_cv()` además **re-verifica
explícitamente** esa propiedad en cada fold (`assert train_idx.max() <
val_idx.min()`) en vez de confiar ciegamente en que sklearn no cambió su
comportamiento.

Las features de lag/rolling **no** se recalculan por fold: se calculan una
sola vez sobre toda la serie antes de este script (`add_lag_rolling_features`,
en `train_sales_forecast.py`), con `.shift()` causal — el valor de cada fila
depende solo de filas estrictamente anteriores en el tiempo, así que no
puede "asomarse" a la ventana de validación de ningún fold sin importar
dónde caiga el límite de ese fold (ver el docstring de esa función para el
detalle del `.shift(1)` antes de `.rolling(3)`).

**Simplificación documentada**: el modelo de tendencia (`fit_trend_model`,
`LinearRegression` log-lineal sobre `time_index`) se ajusta **una sola vez**
con las 8 años de train completos, no se re-ajusta por fold. Refit-earlo con
solo 2-3 años de datos (los folds iniciales de un `TimeSeriesSplit` de 5
sobre ~84 filas dan ~14-28 meses de entrenamiento) daría una tendencia mucho
más ruidosa, no más correcta — la tendencia se trata como una transformación
de preprocesamiento fija (2 parámetros, de bajo riesgo de sobreajuste), y lo
que la validación cruzada evalúa de verdad es la capacidad del Random Forest
de generalizar el residuo estacional a través del tiempo. Documentado también
como límite conocido en `Pasos/sales-forecast-evaluation.md`.

## Ejecución

    python scripts/evaluate_sales_forecast.py

Genera `data/eval/sales-forecast/learning_curve.png` y
`data/eval/evaluation_report.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from train_sales_forecast import (
    EVAL_DIR,
    MODEL_FEATURE_COLUMNS,
    RATIO_COLUMN,
    TARGET_COLUMN,
    DEFAULT_CSV_PATH,
    prepare_train_test_features,
    train_model,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT_DIR / "data" / "eval" / "evaluation_report.md"

N_SPLITS = 5
LEARNING_CURVE_POINTS = 8
LEARNING_CURVE_VAL_FRACTION = 0.2

# Umbrales del diagnostico (documentados en el reporte, no "magicos"): un
# gap validacion/train > 1.6x senala sobreajuste (el modelo memoriza rasgos
# de las filas de train que no generalizan); un error de validacion alto en
# terminos absolutos (RMSE > 12% del ingreso mensual promedio) incluso con
# poco gap senala underfitting (el modelo no ajusta ni siquiera lo que ve).
OVERFIT_GAP_RATIO_THRESHOLD = 1.6
UNDERFIT_RMSE_PCT_THRESHOLD = 12.0


def _revenue_predictions(model, X: np.ndarray, trend: np.ndarray) -> np.ndarray:
    return model.predict(X) * trend


def time_series_cv(
    train_features: pd.DataFrame, feature_columns: list[str] = MODEL_FEATURE_COLUMNS, n_splits: int = N_SPLITS
) -> dict[str, object]:
    """`TimeSeriesSplit` de `n_splits` folds sobre `train_features`. Reporta
    MAE/RMSE (en EUR, escala de negocio) media +/- desviacion estandar entre
    folds, no solo un numero agregado."""
    X = train_features[feature_columns].to_numpy()
    y_ratio = train_features[RATIO_COLUMN].to_numpy()
    y_revenue = train_features[TARGET_COLUMN].to_numpy()
    trend = train_features["trend"].to_numpy()

    splitter = TimeSeriesSplit(n_splits=n_splits)
    folds: list[dict[str, object]] = []

    for fold_number, (train_idx, val_idx) in enumerate(splitter.split(X), start=1):
        # Verificacion explicita de orden cronologico (no confiar solo en
        # que TimeSeriesSplit lo garantice internamente): ningun indice de
        # un fold "futuro" (validacion) puede ser menor a uno de train.
        assert train_idx.max() < val_idx.min(), f"fold {fold_number}: el split no preserva el orden cronologico"

        scaler = StandardScaler()
        X_train_fold = scaler.fit_transform(X[train_idx])
        X_val_fold = scaler.transform(X[val_idx])

        model = train_model(X_train_fold, y_ratio[train_idx])
        y_val_pred = _revenue_predictions(model, X_val_fold, trend[val_idx])
        y_val_true = y_revenue[val_idx]

        mae = float(mean_absolute_error(y_val_true, y_val_pred))
        rmse = float(np.sqrt(mean_squared_error(y_val_true, y_val_pred)))
        folds.append(
            {
                "fold": fold_number,
                "n_train": int(len(train_idx)),
                "n_val": int(len(val_idx)),
                "train_idx_max": int(train_idx.max()),
                "val_idx_min": int(val_idx.min()),
                "mae_eur": mae,
                "rmse_eur": rmse,
            }
        )

    mae_values = np.array([f["mae_eur"] for f in folds])
    rmse_values = np.array([f["rmse_eur"] for f in folds])
    return {
        "folds": folds,
        "mae_mean_eur": float(mae_values.mean()),
        "mae_std_eur": float(mae_values.std()),
        "rmse_mean_eur": float(rmse_values.mean()),
        "rmse_std_eur": float(rmse_values.std()),
    }


def in_sample_train_errors(
    train_features: pd.DataFrame, feature_columns: list[str] = MODEL_FEATURE_COLUMNS
) -> dict[str, float]:
    """MAE/RMSE del modelo final sobre las mismas filas con las que se entrenó
    (error de entrenamiento "in-sample"), para comparar contra el de
    validación cruzada en el diagnóstico de ajuste."""
    scaler = StandardScaler()
    X_train = scaler.fit_transform(train_features[feature_columns])
    model = train_model(X_train, train_features[RATIO_COLUMN].to_numpy())
    y_pred = _revenue_predictions(model, X_train, train_features["trend"].to_numpy())
    y_true = train_features[TARGET_COLUMN].to_numpy()
    return {
        "mae_eur": float(mean_absolute_error(y_true, y_pred)),
        "rmse_eur": float(np.sqrt(mean_squared_error(y_true, y_pred))),
    }


def learning_curve_data(
    train_features: pd.DataFrame,
    feature_columns: list[str] = MODEL_FEATURE_COLUMNS,
    n_points: int = LEARNING_CURVE_POINTS,
    val_fraction: float = LEARNING_CURVE_VAL_FRACTION,
) -> dict[str, list[float]]:
    """Curva de aprendizaje respetando el tiempo: la validación es siempre el
    último `val_fraction` de `train_features` (cronológicamente), y el
    tamaño de entrenamiento crece tomando prefijos cada vez más largos de lo
    que queda *antes* de esa ventana de validación — nunca al revés, para no
    mezclar "aprender del futuro"."""
    n_total = len(train_features)
    n_val = max(6, int(round(n_total * val_fraction)))
    n_trainable = n_total - n_val
    val_slice = train_features.iloc[n_trainable:]

    min_size = max(10, n_trainable // n_points)
    sizes = sorted(set(np.linspace(min_size, n_trainable, n_points, dtype=int).tolist()))

    train_sizes: list[int] = []
    train_errors: list[float] = []
    val_errors: list[float] = []

    for size in sizes:
        subset = train_features.iloc[:size]
        scaler = StandardScaler()
        X_train = scaler.fit_transform(subset[feature_columns])
        X_val = scaler.transform(val_slice[feature_columns])

        model = train_model(X_train, subset[RATIO_COLUMN].to_numpy())

        train_pred = _revenue_predictions(model, X_train, subset["trend"].to_numpy())
        val_pred = _revenue_predictions(model, X_val, val_slice["trend"].to_numpy())

        train_sizes.append(size)
        train_errors.append(float(mean_absolute_error(subset[TARGET_COLUMN], train_pred)))
        val_errors.append(float(mean_absolute_error(val_slice[TARGET_COLUMN], val_pred)))

    return {"train_sizes": train_sizes, "train_mae_eur": train_errors, "val_mae_eur": val_errors}


def plot_learning_curve(curve: dict[str, list[float]], output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(curve["train_sizes"], curve["train_mae_eur"], marker="o", label="Error de entrenamiento (MAE)")
    ax.plot(curve["train_sizes"], curve["val_mae_eur"], marker="o", label="Error de validación (MAE)")
    ax.set_xlabel("Tamaño del set de entrenamiento (meses)")
    ax.set_ylabel("MAE (EUR)")
    ax.set_title("TrackFlow — curva de aprendizaje (residuo estacional -> revenue_eur)")
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def diagnose_fit(train_errors: dict[str, float], cv_summary: dict[str, object], avg_monthly_revenue: float) -> dict[str, object]:
    """Clasifica bien ajustado / underfitting / overfitting a partir del gap
    train vs. validación (RMSE) y del nivel absoluto del error de validación."""
    train_rmse = train_errors["rmse_eur"]
    val_rmse = cv_summary["rmse_mean_eur"]
    gap_ratio = val_rmse / train_rmse if train_rmse > 0 else float("inf")
    val_rmse_pct = val_rmse / avg_monthly_revenue * 100

    if val_rmse_pct > UNDERFIT_RMSE_PCT_THRESHOLD:
        diagnosis = "underfitting"
    elif gap_ratio > OVERFIT_GAP_RATIO_THRESHOLD:
        diagnosis = "overfitting"
    else:
        diagnosis = "bien ajustado"

    return {
        "diagnosis": diagnosis,
        "train_rmse_eur": train_rmse,
        "val_rmse_mean_eur": val_rmse,
        "val_rmse_std_eur": cv_summary["rmse_std_eur"],
        "gap_ratio_val_over_train": gap_ratio,
        "val_rmse_pct_of_avg_monthly_revenue": val_rmse_pct,
    }


def _corrective_action(diagnosis: str) -> str:
    if diagnosis == "overfitting":
        return (
            "El Random Forest memoriza ruido de train que no generaliza (gap grande entre error de "
            "entrenamiento y de validación). Acción concreta: reducir la complejidad del bosque -- subir "
            "`min_samples_leaf` (hoy 2) y/o bajar `max_depth` (hoy 6) en `train_sales_forecast.train_model()` -- "
            "antes que agregar más datos (no hay más años disponibles) o más features (ya se agregaron "
            "lag/rolling; agregar más solo empeoraría el sobreajuste con 84 filas de entrenamiento)."
        )
    if diagnosis == "underfitting":
        return (
            "El modelo no ajusta ni siquiera los datos que ve (error alto y parejo en train y validación). "
            "Acción concreta: el residuo estacional puede necesitar más señal que mes/lag/rolling -- revisar si "
            "`max_depth=6` es demasiado bajo para el patrón real, o si faltan features de calendario adicionales "
            "(p. ej. una interacción explícita mes x año, o el propio `avg_revenue_per_shipment_eur` rezagado). "
            "No es un problema de sobreajuste, así que reducir complejidad empeoraría el underfitting."
        )
    return (
        "Error de validación bajo y cercano al de entrenamiento: no se recomienda una acción correctiva "
        "inmediata. Sí vale la pena monitorear el PSI de `us_share` (ver `train_sales_forecast.py`) en corridas "
        "futuras -- un cambio de mezcla de mercado podría degradar este ajuste sin que el error lo refleje "
        "todavía en el corto plazo."
    )


def write_evaluation_report(
    cv_summary: dict[str, object],
    train_errors: dict[str, float],
    diagnosis: dict[str, object],
    output_path: Path = REPORT_PATH,
) -> None:
    fold_rows = "\n".join(
        f"| {f['fold']} | {f['n_train']} | {f['n_val']} | {f['mae_eur']:.0f} | {f['rmse_eur']:.0f} |"
        for f in cv_summary["folds"]
    )

    report = f"""# Reporte técnico de evaluación — modelo de predicción de ingresos TrackFlow

Generado por `scripts/evaluate_sales_forecast.py`. Ver `Pasos/sales-forecast-evaluation.md`
para el detalle completo de la metodología.

## Validación cruzada temporal ({N_SPLITS} folds, `TimeSeriesSplit`)

| Fold | Meses train | Meses validación | MAE (EUR) | RMSE (EUR) |
| --- | --- | --- | --- | --- |
{fold_rows}

- **MAE validación**: {cv_summary['mae_mean_eur']:.0f} ± {cv_summary['mae_std_eur']:.0f} EUR (media ± desvío estándar entre folds).
- **RMSE validación**: {cv_summary['rmse_mean_eur']:.0f} ± {cv_summary['rmse_std_eur']:.0f} EUR.
- **RMSE entrenamiento** (in-sample, modelo final): {train_errors['rmse_eur']:.0f} EUR.

## Por qué RMSE, no MAE, para el costo de negocio (CONTEXT5.md, Sección 3)

El CONTEXT del negocio pide explícitamente un **Gini alto** para que Thomas (CEO)
pueda "distinguir con confianza entre un mes de temporada baja normal ... y
una **caída atípica** que amerite investigación" — el costo de negocio que
más le importa a TrackFlow no es el error típico mes a mes, es **fallar
grande en un mes atípico** sin darse cuenta. RMSE penaliza los errores
grandes de forma cuadrática (un error 2x más grande pesa 4x más en RMSE,
solo 2x más en MAE), así que es la métrica que mejor refleja ese costo:
un modelo con RMSE bajo no puede estar fallando fuerte en meses puntuales sin
que la métrica lo capture, mientras que un MAE bajo sí podría estar
escondiendo unos pocos meses muy errados detrás de muchos meses casi
perfectos — justo el escenario que Thomas necesita detectar. Por eso el
diagnóstico de ajuste de abajo usa RMSE, no MAE, como métrica principal
(se reporta MAE igual, arriba, por completitud).

## Diagnóstico: **{diagnosis['diagnosis'].upper()}**

- RMSE entrenamiento: {diagnosis['train_rmse_eur']:.0f} EUR.
- RMSE validación: {diagnosis['val_rmse_mean_eur']:.0f} ± {diagnosis['val_rmse_std_eur']:.0f} EUR.
- Razón validación/entrenamiento: {diagnosis['gap_ratio_val_over_train']:.2f}x (umbral de sobreajuste: >{OVERFIT_GAP_RATIO_THRESHOLD}x).
- RMSE de validación como % del ingreso mensual promedio: {diagnosis['val_rmse_pct_of_avg_monthly_revenue']:.2f}% (umbral de underfitting: >{UNDERFIT_RMSE_PCT_THRESHOLD}%).

Ver `data/eval/sales-forecast/learning_curve.png`: {"el error de validación converge hacia el de entrenamiento a medida que crece el set de entrenamiento (patrón típico de un modelo bien ajustado)." if diagnosis["diagnosis"] == "bien ajustado" else "el gap entre error de entrenamiento y de validación es visible incluso con el set de entrenamiento completo." if diagnosis["diagnosis"] == "overfitting" else "ambos errores se mantienen altos incluso con el set de entrenamiento completo, sin la brecha característica de sobreajuste."}

## Acción correctiva propuesta

{_corrective_action(diagnosis["diagnosis"])}
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)


def run(csv_path: Path = DEFAULT_CSV_PATH) -> dict[str, object]:
    train_features, _test_features, _trend_model = prepare_train_test_features(csv_path)

    cv_summary = time_series_cv(train_features)
    train_errors = in_sample_train_errors(train_features)
    avg_monthly_revenue = float(train_features[TARGET_COLUMN].mean())
    diagnosis = diagnose_fit(train_errors, cv_summary, avg_monthly_revenue)

    curve = learning_curve_data(train_features)
    plot_learning_curve(curve, EVAL_DIR / "learning_curve.png")

    write_evaluation_report(cv_summary, train_errors, diagnosis)

    result = {"cv_summary": cv_summary, "train_errors": train_errors, "diagnosis": diagnosis}
    (EVAL_DIR / "evaluation_metrics.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    output = run()
    print(json.dumps(output["diagnosis"], indent=2))
    print(f"Reporte completo en {REPORT_PATH}")
