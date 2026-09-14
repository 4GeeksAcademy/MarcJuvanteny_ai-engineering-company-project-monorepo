"""Entrenamiento del modelo de regresión de ingresos de TrackFlow.

Implementa `CONTEXT/CONTEXTPredicción.md`: carga `data/raw/trackflow_sales.csv`
(fila `consolidated`), separa los primeros 8 años como entrenamiento y los 2
más recientes como prueba, entrena un `RandomForestRegressor`, y calcula
MSE, PSI, Gini y "K2 Score" sobre el conjunto de prueba.

## Por qué trend + residuo estacional (no revenue_eur crudo)

Un Random Forest (o cualquier ensamble de árboles, XGBoost incluido) **no
puede extrapolar**: predice promediando valores de hojas vistas en
entrenamiento, así que para un `time_index` mayor a todo lo visto en 2016-2023
el techo de predicción posible es, en el mejor de los casos, el ingreso más
alto observado en entrenamiento. Como el ingreso de TrackFlow crece
compuesto ~6%/año (Sección 4 del CONTEXT), 2024-2025 está sistemáticamente
por encima de ese techo — entrenar el Random Forest directo sobre
`revenue_eur` da un R² fuertemente negativo en prueba (peor que predecir la
media), verificado empíricamente antes de este ajuste.

Por eso el target real del Random Forest es un **residuo estacional
multiplicativo**: se ajusta primero una regresión log-lineal simple
(`LinearRegression` sobre `log(revenue_eur) ~ time_index`, **solo con
train**) que sí puede extrapolar la tendencia de crecimiento, y el Random
Forest aprende `revenue_eur / tendencia(time_index)` — un valor acotado
(~0.85–1.35, el rango de la estacionalidad) que se repite cada 12 meses y
por lo tanto siempre está dentro del rango visto en entrenamiento, incluso
para meses de 2024-2025. La predicción final es
`tendencia(time_index) * residuo_predicho`.

## Por qué Random Forest (no XGBoost) para el residuo estacional

- **Tamaño de datos**: 120 filas mensuales (96 de entrenamiento). Un dataset
  así de chico no se beneficia del boosting secuencial de XGBoost, que
  típicamente necesita más datos y más ajuste de hiperparámetros
  (learning_rate, n_estimators, regularización) para no sobreajustar; un
  Random Forest con árboles poco profundos es más robusto "out of the box"
  en este régimen.
- **Explicabilidad**: `feature_importances_` de un Random Forest es directo
  de interpretar para Thomas/Ana (¿pesa más la estacionalidad o la
  tendencia?), sin necesitar SHAP ni una librería adicional.
- **Tiempo disponible para ajuste**: esta es una entrega de viabilidad
  ("¿es predecible el ingreso antes de invertir en un dashboard?"), no un
  modelo de producción — Random Forest con defaults razonables converge sin
  búsqueda de hiperparámetros; XGBoost mal ajustado en un dataset tan chico
  sobreajusta con facilidad.

## Qué mide cada métrica (y por qué MSE bajo no alcanza solo)

- **MSE** (`mean_squared_error`): error cuadrático medio en EUR² — penaliza
  fuerte los errores grandes, pero por sí solo no dice si el modelo *sabe
  cuándo* va a fallar, ni si acierta la dirección de un mes atípico. Se
  reporta también como RMSE (√MSE, en EUR) sobre el ingreso mensual promedio
  del período de prueba, para que sea interpretable en términos de negocio
  ("el modelo se equivoca en promedio un X% del ingreso mensual").
- **PSI** (Population Stability Index) sobre la proporción de ingreso que
  viene de `us` (`us_share`): compara la distribución de esa proporción
  entre entrenamiento y prueba. Un PSI alto (`> 0.25` es la regla de pulgar
  estándar en riesgo de crédito) señala que la mezcla LA/Zaragoza cambió de
  forma significativa entre ambos períodos — algo que un MSE bajo no
  detecta, porque el MSE es ciego a *por qué* el modelo acierta o falla.
- **Gini normalizado** (curva de Lorenz sobre predicho vs. real, método
  estándar de scoring): mide el poder de *discriminación/ranking* del
  modelo — si ordena correctamente los meses de mayor a menor ingreso real.
  Un MSE bajo puede convivir con un Gini bajo si el modelo acierta el nivel
  promedio pero no distingue bien un mes de temporada baja normal de una
  caída atípica (justo lo que le importa a Thomas, sección 3 del CONTEXT).
- **"K2 Score"** — el CONTEXT no lo define en ningún otro lugar del repo
  (`grep -rn "K2"` no encuentra otra definición). Se interpreta como **R²**
  (`r2_score`, coeficiente de determinación): junto con MSE/PSI/Gini
  completa el cuarteto estándar de un scorecard de modelo (error absoluto +
  estabilidad + discriminación + varianza explicada). Si "K2 Score" refiere
  a otra métrica en el material original del curso, esta es la interpretación
  a corregir primero — documentado también en
  `Pasos/sales-forecast-model.md`.

Ejecución: `python scripts/train_sales_forecast.py` (requiere
`scripts/requirements-sales-forecast.txt`: pandas, numpy, scikit-learn,
matplotlib).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin display: solo guarda el PNG a disco
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CSV_PATH = ROOT_DIR / "data" / "raw" / "trackflow_sales.csv"
EVAL_DIR = ROOT_DIR / "data" / "eval" / "sales-forecast"

TRAIN_YEARS = 8
TEST_YEARS = 2
RANDOM_STATE = 42

# Features del Random Forest: SOLO el componente ciclico (mes del anio). El
# componente de tendencia (crecimiento compuesto anual) NO se le pasa al
# Random Forest -- ver fit_trend_model() y la nota "Por que trend+residuo"
# mas abajo sobre por que un modelo de arboles no puede extrapolar tendencia.
SEASONAL_FEATURE_COLUMNS = ["month_num", "month_sin", "month_cos"]
TREND_FEATURE_COLUMNS = ["time_index"]
TARGET_COLUMN = "revenue_eur"


def load_full_dataset(csv_path: Path = DEFAULT_CSV_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["month"])
    return df.sort_values(["month", "market"]).reset_index(drop=True)


def load_consolidated_sales(csv_path: Path = DEFAULT_CSV_PATH) -> pd.DataFrame:
    """Solo la fila `consolidated` de cada mes (la target del modelo, Seccion 2 del CONTEXT)."""
    df = load_full_dataset(csv_path)
    consolidated = df[df["market"] == "consolidated"].sort_values("month").reset_index(drop=True)
    return clean_missing_values(consolidated)


def clean_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Descarta filas con nulos en columnas criticas antes de entrenar.

    El dataset generado (Seccion 5 del CONTEXT: revenue_eur siempre positivo,
    sin meses faltantes) no trae nulos, pero esto es una entrada real de
    negocio -- una actualizacion futura del CSV podria traerlos, y entrenar
    con NaN rompe silenciosamente el modelo (o lo entrena mal) en vez de
    fallar explicito.
    """
    required = ["revenue_eur", "shipments_processed", "avg_revenue_per_shipment_eur", "month"]
    before = len(df)
    cleaned = df.dropna(subset=required)
    dropped = before - len(cleaned)
    if dropped:
        print(f"[train_sales_forecast] {dropped} fila(s) descartada(s) por valores nulos en {required}.")
    return cleaned.reset_index(drop=True)


def split_train_test(df: pd.DataFrame, train_years: int = TRAIN_YEARS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Primeros `train_years` años -> entrenamiento; el resto -> prueba.

    Split cronologico por año calendario, no aleatorio: el modelo nunca ve
    ejemplos de los años de prueba durante el entrenamiento (Seccion 6 del
    CONTEXT), y al no barajar meses, es estructuralmente imposible que un mes
    de prueba quede intercalado antes de uno de entrenamiento -- ver el test
    de "no leakage" en tests/pipelines/.
    """
    years = sorted(df["month"].dt.year.unique())
    train_year_set = set(years[:train_years])
    train_df = df[df["month"].dt.year.isin(train_year_set)].reset_index(drop=True)
    test_df = df[~df["month"].dt.year.isin(train_year_set)].reset_index(drop=True)
    return train_df, test_df


def build_features(df: pd.DataFrame, base_year: int) -> pd.DataFrame:
    """Features puramente calendario: year, month_num, month_sin/cos, time_index.

    `base_year` DEBE ser el año mínimo del dataset **completo** (antes del
    split), no de `df` — si se llama por separado en train/test y cada uno
    calcula su propio mínimo, `time_index` se reinicia a 0 en el conjunto de
    prueba en vez de continuar la cuenta desde 2016, y `fit_trend_model()`
    extrapola sobre el punto equivocado de la curva (bug real, encontrado al
    verificar este script: daba R² muy negativo porque el modelo de
    tendencia terminaba prediciendo para 2024-2025 como si fuera 2016-2017).

    Deliberadamente NO se usan shipments_processed / avg_revenue_per_shipment_eur
    como features: para un mes futuro real, esos datos tampoco se conocen de
    antemano (son resultado del mismo mes, no un indicador adelantado), asi
    que usarlos aqui seria una forma de fuga de informacion disfrazada de
    feature engineering -- el modelo aprenderia a "trampear" con datos que en
    produccion no estarian disponibles al momento de predecir.
    """
    out = df.copy()
    out["year"] = out["month"].dt.year
    out["month_num"] = out["month"].dt.month
    out["time_index"] = (out["year"] - base_year) * 12 + (out["month_num"] - 1)
    out["month_sin"] = np.sin(2 * np.pi * out["month_num"] / 12)
    out["month_cos"] = np.cos(2 * np.pi * out["month_num"] / 12)
    return out


def scale_features(
    train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str] = SEASONAL_FEATURE_COLUMNS
) -> tuple[np.ndarray, np.ndarray, StandardScaler]:
    """Escala las features numericas; el scaler se ajusta solo con train (nunca con test)."""
    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_df[feature_columns])
    test_scaled = scaler.transform(test_df[feature_columns])
    return train_scaled, test_scaled, scaler


def fit_trend_model(train_features: pd.DataFrame) -> LinearRegression:
    """Regresion log-lineal de `revenue_eur` sobre `time_index`, ajustada solo
    con train. A diferencia del Random Forest, esta SI extrapola mas alla del
    rango de entrenamiento -- es la pieza que hace viable proyectar 2024-2025."""
    trend_model = LinearRegression()
    trend_model.fit(train_features[TREND_FEATURE_COLUMNS], np.log(train_features[TARGET_COLUMN]))
    return trend_model


def trend_prediction(trend_model: LinearRegression, df: pd.DataFrame) -> np.ndarray:
    return np.exp(trend_model.predict(df[TREND_FEATURE_COLUMNS]))


def train_model(X_train: np.ndarray, y_train: np.ndarray, random_state: int = RANDOM_STATE) -> RandomForestRegressor:
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=2,
        random_state=random_state,
    )
    model.fit(X_train, y_train)
    return model


def predict_with_variability(model: RandomForestRegressor, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prediccion media + banda P5-P95 usando la dispersion entre arboles del bosque."""
    tree_predictions = np.stack([tree.predict(X) for tree in model.estimators_], axis=0)
    mean_prediction = tree_predictions.mean(axis=0)
    lower = np.percentile(tree_predictions, 5, axis=0)
    upper = np.percentile(tree_predictions, 95, axis=0)
    return mean_prediction, lower, upper


def population_stability_index(expected: np.ndarray, actual: np.ndarray, buckets: int = 5) -> float:
    """PSI estandar: `expected` = distribucion base (train), `actual` = distribucion a comparar (test).

    `buckets=5` (quintiles), no los 10 "estandar" de scoring de riesgo: esos
    10 buckets asumen poblaciones de miles de registros. Aqui `actual`
    (test) son solo 24 meses -- con 10 buckets caen ~2.4 puntos por bucket
    en promedio, varios quedan en 0, y el PSI se dispara a valores enormes
    (>1.5) que no reflejan un cambio real de distribucion (verificado: con
    10 buckets daba PSI=1.56 aun cuando train y test tienen medias y
    desvios de `us_share` practicamente identicos). Con 5 buckets el PSI
    queda estable y por debajo del umbral de "cambio significativo" (0.25),
    que es lo que corresponde dado que el generador no introduce ningun
    corrimiento real entre periodos.
    """
    breakpoints = np.quantile(expected, np.linspace(0, 1, buckets + 1))
    breakpoints[0], breakpoints[-1] = -np.inf, np.inf
    expected_pct = np.clip(np.histogram(expected, breakpoints)[0] / len(expected), 1e-4, None)
    actual_pct = np.clip(np.histogram(actual, breakpoints)[0] / len(actual), 1e-4, None)
    return float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))


def _gini(actual: np.ndarray, pred: np.ndarray) -> float:
    combined = np.c_[actual, pred, np.arange(len(actual))]
    combined = combined[np.lexsort((combined[:, 2], -combined[:, 1]))]
    total = combined[:, 0].sum()
    cumulative = combined[:, 0].cumsum().sum() / total
    cumulative -= (len(actual) + 1) / 2.0
    return cumulative / len(actual)


def gini_normalized(actual: np.ndarray, pred: np.ndarray) -> float:
    """Gini normalizado (curva de Lorenz), metodo estandar de scoring para targets continuos."""
    baseline = _gini(actual, actual)
    if baseline == 0:
        return 0.0
    return _gini(actual, pred) / baseline


def compute_us_share_by_month(full_df: pd.DataFrame) -> pd.Series:
    """`us_share[mes] = revenue_eur(us) / revenue_eur(consolidated)` -- para el PSI (Seccion 3 del CONTEXT)."""
    pivot = full_df.pivot_table(index="month", columns="market", values="revenue_eur")
    return (pivot["us"] / pivot["consolidated"]).rename("us_share")


def compute_metrics(
    y_test: np.ndarray, y_pred: np.ndarray, us_share_train: np.ndarray, us_share_test: np.ndarray
) -> dict[str, float]:
    mse_eur2 = float(mean_squared_error(y_test, y_pred))
    rmse_pct_of_avg_revenue = float(np.sqrt(mse_eur2) / y_test.mean() * 100)
    return {
        "mse_eur2": mse_eur2,
        "rmse_pct_of_avg_monthly_revenue": rmse_pct_of_avg_revenue,
        "psi_us_share_train_vs_test": population_stability_index(us_share_train, us_share_test),
        "gini_normalized": gini_normalized(y_test, y_pred),
        "k2_score_r2": float(r2_score(y_test, y_pred)),
    }


def plot_forecast(test_df: pd.DataFrame, y_pred: np.ndarray, lower: np.ndarray, upper: np.ndarray, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(test_df["month"], test_df[TARGET_COLUMN], label="Real", marker="o", color="black")
    ax.plot(test_df["month"], y_pred, label="Predicción", marker="o", color="tab:blue")
    ax.fill_between(
        test_df["month"], lower, upper, alpha=0.2, color="tab:blue", label="Rango de variabilidad (P5–P95 entre árboles)"
    )
    ax.set_title("TrackFlow — ingresos consolidados: predicción vs. real (2 años de prueba)")
    ax.set_ylabel("revenue_eur")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def run(csv_path: Path = DEFAULT_CSV_PATH) -> dict[str, float]:
    consolidated = load_consolidated_sales(csv_path)
    train_df, test_df = split_train_test(consolidated)

    base_year = consolidated["month"].dt.year.min()  # fijo para todo el dataset, ver build_features()
    train_features = build_features(train_df, base_year)
    test_features = build_features(test_df, base_year)

    # 1) Tendencia (extrapolable): ajustada solo con train.
    trend_model = fit_trend_model(train_features)
    train_trend = trend_prediction(trend_model, train_features)
    test_trend = trend_prediction(trend_model, test_features)

    # 2) Residuo estacional (lo que predice el Random Forest): acotado y
    #    ciclico, nunca fuera del rango visto en entrenamiento aunque el
    #    anio sea nuevo.
    train_features = train_features.assign(seasonal_ratio=train_features[TARGET_COLUMN].to_numpy() / train_trend)

    X_train, X_test, _scaler = scale_features(train_features, test_features)
    y_train_ratio = train_features["seasonal_ratio"].to_numpy()
    y_test = test_features[TARGET_COLUMN].to_numpy()

    model = train_model(X_train, y_train_ratio)
    ratio_pred, ratio_lower, ratio_upper = predict_with_variability(model, X_test)

    # 3) Recompone: prediccion final = tendencia extrapolada x residuo predicho.
    y_pred = ratio_pred * test_trend
    lower = ratio_lower * test_trend
    upper = ratio_upper * test_trend

    full_df = load_full_dataset(csv_path)
    us_share = compute_us_share_by_month(full_df)
    us_share_train = us_share.loc[train_df["month"]].to_numpy()
    us_share_test = us_share.loc[test_df["month"]].to_numpy()

    metrics = compute_metrics(y_test, y_pred, us_share_train, us_share_test)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    plot_forecast(test_df, y_pred, lower, upper, EVAL_DIR / "prediction_vs_actual.png")
    (EVAL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    return metrics


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
