# TrackFlow — Modelo de predicción de ingresos (regresión)

Fecha: 2026-09-14

Implementación de `CONTEXT/CONTEXTPredicción.md`: viabilidad de predecir el
ingreso mensual consolidado de TrackFlow antes de invertir en un dashboard
ejecutivo (Thomas, CEO). Cubre las 5 secciones del checklist de la guía:
preparación de datos, entrenamiento, evaluación, visualización y pruebas.

## El dataset no existía — se generó

`CONTEXT/CONTEXTPredicción.md` (sección 2) dice que
`data/raw/trackflow_sales.csv` "ya está incluido en tu monorepo", pero no
estaba (`data/raw/` solo tenía los README). La sección 4 del CONTEXT sí
documenta el patrón generador con suficiente detalle para reconstruirlo de
forma determinista (`random_state=42`): 10 años mensuales (2016-01 a
2025-12), crecimiento anual que alterna entre `6%+3%=9%` y `6%-3%=3%`,
estacionalidad Nov-Dic +25-35%/Feb -10-15%/resto ±5%, split ~60/40 US/España.

[`scripts/generate_trackflow_sales_dataset.py`](../scripts/generate_trackflow_sales_dataset.py)
implementa exactamente esas reglas y generó
[`data/raw/trackflow_sales.csv`](../data/raw/trackflow_sales.csv) (360 filas:
120 `consolidated` + 120 `us` + 120 `spain`). Lo único que el CONTEXT no
especifica es el punto de partida absoluto (ingreso de enero 2016) y el
ingreso medio por envío — elecciones propias del generador, documentadas en
su docstring, sin impacto en la validez de las reglas de crecimiento/
estacionalidad que sí están especificadas.

## Dónde vive el código

```
scripts/
  generate_trackflow_sales_dataset.py   # genera data/raw/trackflow_sales.csv (determinista, seed=42)
  train_sales_forecast.py               # carga, split 8/2 años, entrena, evalúa, grafica
  requirements-sales-forecast.txt       # pandas, numpy, scikit-learn, matplotlib, pytest

tests/pipelines/
  test_sales_forecast_split.py          # valida el split 8/2 años + no data leakage

data/eval/sales-forecast/
  prediction_vs_actual.png              # visualización (generada al correr el script)
  metrics.json                          # MSE, PSI, Gini, K2 Score (generado al correr el script)
```

`tests/pipelines/` es una carpeta nueva en la raíz del repo — no confundir
con `data/pipelines/tests/` (tests del pipeline de KPIs semanal, Hito 6, ver
`Pasos/telemetria-pipeline-implementacion.md`) ni con `scripts/tests/`
(tests de `nightly_export.py`, ver
`Pasos/telemetria-nightly-export-job-runner.md`): son tres suites de test
independientes, en tres ubicaciones distintas, cada una junto al código que
le corresponde según dónde la pidió cada guía.

## Cómo correrlo

```bash
cd scripts
python3 -m venv .venv-sales-forecast
source .venv-sales-forecast/bin/activate
pip install -r requirements-sales-forecast.txt

python generate_trackflow_sales_dataset.py   # una sola vez, genera el CSV
python train_sales_forecast.py               # entrena + evalúa + grafica
python -m pytest ../tests/pipelines/ -q      # test del split
```

## Checklist de la entrega — Preparación de datos

- [x] **Carga el dataset desde la ruta correspondiente**:
  `data/raw/trackflow_sales.csv` (`load_consolidated_sales()`), columnas
  verificadas contra la sección 2 del CONTEXT (`month`, `revenue_eur`,
  `shipments_processed`, `avg_revenue_per_shipment_eur`, `market`).
- [x] **Trata los valores nulos o vacíos antes de entrenar**: `clean_missing_values()`
  descarta filas con nulos en las columnas críticas y **loguea cuántas**
  (el dataset generado no trae ninguna — sección 5 del CONTEXT — así que
  esto es una salvaguarda para una actualización futura del CSV real, no
  algo que se ejercite hoy).
- [x] **Split entrenamiento (8 primeros años) / prueba (2 más recientes),
  el modelo nunca ve los años de prueba durante el entrenamiento**:
  `split_train_test()` — partición por año calendario (2016-2023 train,
  2024-2025 test), no aleatoria ni barajada. Verificado en
  `tests/pipelines/test_sales_forecast_split.py` (ver "Pruebas" abajo).
- [x] **Escala las variables que lo requieren**: `scale_features()` —
  `StandardScaler` ajustado **solo con train**, aplicado a las features
  estacionales (`month_num`, `month_sin`, `month_cos`) antes de entrenar el
  Random Forest. (Nota técnica: un Random Forest en sí es invariante a
  escalado monotónico — no lo necesita para su exactitud — pero se
  implementa igual, ajustado correctamente solo con train, tanto porque la
  guía lo pide explícitamente como porque deja el pipeline listo para un
  modelo sensible a escala si se cambia más adelante.)

## Checklist de la entrega — Entrenamiento del modelo

- [x] **Regresión con XGBoost o Random Forest (elegí uno) con scikit-learn**:
  `RandomForestRegressor` (`train_model()`).
- [x] **Criterio de elección documentado**: en el docstring de
  `train_sales_forecast.py` (sección "Por qué Random Forest") — tamaño de
  datos (120 filas, muy chico para el boosting secuencial de XGBoost),
  explicabilidad (`feature_importances_` directo, sin SHAP), y tiempo
  disponible (esta es una entrega de *viabilidad*, no un modelo de
  producción — Random Forest converge con defaults razonables sin búsqueda
  de hiperparámetros).

## Checklist de la entrega — Evaluación

- [x] **MSE, PSI, Gini y K2 Score sobre el conjunto de prueba**:
  `compute_metrics()`. Resultado real de esta entrega (ver "Resultado final"
  abajo).
- [x] **Qué mide cada métrica y por qué un MSE bajo no alcanza solo**:
  documentado en el docstring de `train_sales_forecast.py` (sirve como el
  "README de tu implementación" que pide la guía) y resumido acá:

  | Métrica | Qué mide | Por qué el MSE solo no alcanza |
  | --- | --- | --- |
  | **MSE** (EUR², + RMSE como % del ingreso mensual promedio) | Error cuadrático medio — penaliza fuerte los errores grandes. | No dice *si el modelo sabe cuándo* va a fallar, ni si distingue bien un mes normal de uno atípico. |
  | **PSI** sobre `us_share` (proporción de ingreso que viene de `us`) | Si la mezcla LA/Zaragoza cambió de forma significativa entre train y test (sección 3 del CONTEXT). | El MSE es ciego a *por qué* el modelo acierta o falla — un cambio de mezcla de mercado podría invalidar el modelo sin que el MSE lo refleje todavía. |
  | **Gini normalizado** (curva de Lorenz, predicho vs. real) | Poder de *discriminación/ranking*: si el modelo ordena los meses de mayor a menor ingreso real. | Un MSE bajo puede convivir con Gini bajo si el modelo acierta el nivel promedio pero no distingue una caída atípica de una temporada baja normal — justo lo que le importa a Thomas. |
  | **"K2 Score"** (interpretado como **R²**, ver nota) | Varianza explicada del target por el modelo. | Completa el cuarteto: error absoluto + estabilidad + discriminación + varianza explicada — ninguna de las otras tres sustituye a esta. |

  > **Nota sobre "K2 Score":** el CONTEXT no lo define en ningún otro lugar
  > del repo (`grep -rn "K2"` solo encuentra esta única mención). Se
  > interpretó como **R² (`r2_score`)** — es el candidato más plausible para
  > completar el cuarteto MSE/PSI/Gini/? de un scorecard de modelo, y "K2"
  > es visualmente/fonéticamente parecido a "R2". Si el material original
  > del curso define "K2 Score" como otra cosa, esta es la primera
  > interpretación a corregir — queda señalado también en el docstring del
  > script.

## Checklist de la entrega — Visualización

- [x] **Predicción + rango de variabilidad vs. datos reales de los 2 años de
  prueba**: `plot_forecast()` → [`data/eval/sales-forecast/prediction_vs_actual.png`](../data/eval/sales-forecast/prediction_vs_actual.png).
  El rango de variabilidad se calcula con la dispersión **entre los árboles
  individuales** del Random Forest (percentil 5–95 de las predicciones de
  cada uno de los 300 árboles por mes, `predict_with_variability()`), no un
  intervalo de confianza paramétrico — es la forma más directa de obtener
  incertidumbre de un ensamble de árboles sin dependencias adicionales.

## Checklist de la entrega — Pruebas

- [x] **Prueba unitaria en `tests/pipelines/`** que valida el split 8/2 años
  y que no hay fuga de datos: `tests/pipelines/test_sales_forecast_split.py`
  (5 tests) — cobertura de años exacta (2016-2023 / 2024-2025), conteo de
  filas (96/24), sin solapamiento de meses, **orden cronológico estricto**
  (`train.max() < test.min()`, la prueba real de "no leakage": no solo que
  no se solapen, sino que ningún mes de prueba pueda quedar intercalado
  antes de terminar el entrenamiento), invariancia al orden de las filas de
  entrada, y una prueba de integración liviana contra el CSV real generado
  (se salta con un mensaje claro si el CSV no existe, en vez de fallar
  oscuro).

## Bugs reales encontrados y corregidos al verificar

Ejecuté el pipeline de punta a punta (no me quedé en "el código compila") y
aparecieron dos problemas reales que cambiaron el resultado de forma
sustancial:

1. **El modelo no podía extrapolar la tendencia.** La primera versión
   entrenaba el Random Forest directo sobre `revenue_eur`. Un ensamble de
   árboles predice promediando hojas vistas en entrenamiento — no puede
   proyectar más allá del rango de valores que vio. Como el ingreso de
   TrackFlow crece compuesto ~6%/año, 2024-2025 queda sistemáticamente por
   encima de todo lo visto en 2016-2023, y el modelo predecía por debajo de
   forma consistente: **R² = -6.5** (peor que predecir la media). Esto no es
   un problema de "elegí mal entre XGBoost y Random Forest" — cualquier
   ensamble de árboles tiene la misma limitación. La solución: descomponer
   en tendencia (ajustada con una regresión log-lineal simple sobre
   `time_index`, que sí extrapola) + residuo estacional multiplicativo
   (`revenue_eur / tendencia`, acotado y cíclico, eso sí lo predice bien el
   Random Forest porque nunca sale del rango visto). Ver la sección "Por qué
   trend + residuo estacional" en el docstring del script.
2. **`time_index` se reiniciaba a 0 en el conjunto de prueba.** Con el fix
   de arriba, el resultado seguía mal (R² = -7.9) — un segundo bug: las
   features se construían llamando `build_features()` por separado en train
   y test, y cada llamada calculaba `year.min()` sobre **su propio**
   subconjunto — para test (2024-2025), `time_index` volvía a arrancar en 0
   en vez de continuar desde 96 (donde termina train). El modelo de
   tendencia extrapolaba para el punto equivocado de la curva (como si 2024
   fuera 2016). Arreglado pasando un `base_year` fijo (el mínimo del
   dataset completo, calculado **antes** del split) a ambas llamadas de
   `build_features()`. Con los dos fixes: **R² = 0.86**.
3. **PSI con 10 buckets "estándar" se disparaba a 1.56** con medias y
   desvíos de `us_share` prácticamente idénticos entre train y test (0.6003
   vs 0.6001) — un falso positivo de "cambio de mezcla de mercado" severo.
   Causa: PSI con 10 buckets asume poblaciones de miles de registros; con
   solo 24 meses de prueba repartidos en 10 buckets caen ~2.4 puntos por
   bucket en promedio, varios en 0, y el PSI se infla artificialmente por
   el tamaño de muestra, no por un cambio real. Con 5 buckets (quintiles,
   ~4.8 puntos/bucket) el PSI baja a 0.176 — por debajo del umbral estándar
   de "cambio significativo" (0.25), que es lo correcto dado que el
   generador no introduce ningún corrimiento real entre períodos.

## Resultado final (sobre 2024-2025)

```json
{
  "mse_eur2": 412209223.52,
  "rmse_pct_of_avg_monthly_revenue": 4.75,
  "psi_us_share_train_vs_test": 0.176,
  "gini_normalized": 0.912,
  "k2_score_r2": 0.859
}
```

Lectura para Thomas: el modelo explica el 86% de la varianza del ingreso
mensual de prueba (R²), se equivoca en promedio ~4.75% del ingreso mensual
(RMSE), distingue bien los meses de mayor/menor ingreso (Gini 0.91), y no
hay señal de que la mezcla LA/Zaragoza haya cambiado de forma significativa
entre 2016-2023 y 2024-2025 (PSI 0.18) — **sí parece viable** invertir en el
dashboard ejecutivo basado en este enfoque, con la salvedad de que es un
dataset sintético (ver "Pendiente" abajo).

## Decisiones de implementación no cubiertas por la guía genérica

- **Dataset generado, no provisto**: ver la sección de arriba. Todas las
  reglas de negocio documentadas (crecimiento, estacionalidad, split de
  mercado, sin huecos, siempre positivo) se siguieron al pie de la letra;
  solo el punto de partida absoluto es una elección propia.
- **Features del Random Forest excluyen `shipments_processed` /
  `avg_revenue_per_shipment_eur`**: para un mes futuro real esos datos
  tampoco se conocen de antemano (son resultado del mismo mes que se quiere
  predecir, no un indicador adelantado) — incluirlos sería fuga de
  información disfrazada de feature engineering, no una feature legítima
  para pronóstico.
- **Descomposición trend + residuo estacional**: no pedida explícitamente
  por la guía, pero necesaria para que un modelo de árboles funcione en
  absoluto sobre una serie con tendencia creciente — ver "Bugs reales
  encontrados" arriba. Se mantiene "Random Forest" como el modelo elegido
  (es el que predice el residuo); la tendencia usa una regresión lineal
  simple auxiliar, no un segundo modelo "candidato".

## Pendiente / siguientes pasos

1. El dataset es sintético (generado, no datos reales de TrackFlow) — el
   modelo es una prueba de viabilidad de la *metodología*, no una
   predicción utilizable en producción hasta correr esto contra ingresos
   reales.
2. Reconciliar "K2 Score" con la definición real si aparece en otro material
   del curso no visible en este repo (ver la nota en "Evaluación" arriba).
3. No se buscaron hiperparámetros (ni para el Random Forest ni para la
   regresión de tendencia) — quedó documentado como parte deliberada del
   criterio de elección ("tiempo disponible para ajuste"), no como una
   omisión.
