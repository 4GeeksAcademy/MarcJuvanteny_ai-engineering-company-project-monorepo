# TrackFlow — Evaluación rigurosa del modelo de predicción de ingresos

Fecha: 2026-09-23

Continuación de `Pasos/sales-forecast-model.md`, implementando la guía
"Evaluación de un Modelo de Regresión" (`CONTEXT/CONTEXT5.md`): dataset real
(reemplaza el sintético de la entrega anterior), features de lag/rolling,
validación cruzada temporal, curva de aprendizaje, MAE/RMSE, y un reporte
técnico de diagnóstico.

Fuentes leídas antes de implementar, como pidió el mensaje: `CONTEXT/sales.md`
(dataset real) y `CONTEXT/CONTEXT5.md` (guía actualizada — mismo contenido
que `CONTEXT/CONTEXTPredicción.md` salvo la Sección 6, que ahora exige
features de lag/rolling).

## El dataset ya no es sintético

`Pasos/sales-forecast-model.md` documentó que `data/raw/trackflow_sales.csv`
no existía y lo generé sintéticamente. Esta vez `CONTEXT/sales.md` trae el
CSV **real** (120 filas `consolidated`, mismas columnas, 2016-01 a 2025-12,
sin nulos, todo positivo). `scripts/generate_trackflow_sales_dataset.py` se
reescribió para leer esas filas reales (`load_real_consolidated_rows()`) en
vez de sintetizarlas — solo el split `us`/`spain` sigue siendo sintético
(~60/40 con ruido), porque `sales.md` no lo trae y la Sección 5 del CONTEXT5
explícitamente permite aproximarlo así. `data/raw/trackflow_sales.csv` se
regeneró con los datos reales.

Con datos reales el modelo de la entrega anterior (sin cambios de código,
solo el dataset) ya mejoró: R² pasó de 0.86 a 0.93, RMSE de 4.75% a 3.41%
del ingreso mensual promedio, y PSI de 0.18 a 0.06 — la serie real tiene
una estacionalidad más regular que la sintética.

## Dónde vive el código

```
scripts/
  generate_trackflow_sales_dataset.py   # ahora lee CONTEXT/sales.md (real) en vez de sintetizar
  train_sales_forecast.py               # + lag/rolling features, prepare_train_test_features() compartida
  evaluate_sales_forecast.py            # NUEVO: CV temporal, curva de aprendizaje, MAE/RMSE, reporte

tests/pipelines/
  test_sales_forecast_split.py          # (sin cambios) split 8/2 años
  test_timeseries_cv_order.py           # NUEVO: orden cronológico de TimeSeriesSplit

data/eval/
  evaluation_report.md                  # NUEVO: diagnóstico + acción correctiva
  sales-forecast/
    learning_curve.png                  # NUEVO
    evaluation_metrics.json             # NUEVO: CV + diagnóstico en crudo
    prediction_vs_actual.png            # regenerado con datos reales + lag features
    metrics.json                        # regenerado con datos reales + lag features
```

## Cómo correrlo

```bash
cd scripts
source .venv-sales-forecast/bin/activate   # o crear uno nuevo con requirements-sales-forecast.txt

python generate_trackflow_sales_dataset.py   # regenera el CSV desde CONTEXT/sales.md
python train_sales_forecast.py               # entrena + evalúa sobre el split de prueba
python evaluate_sales_forecast.py            # CV temporal + curva de aprendizaje + reporte
python -m pytest ../tests/pipelines/ -q      # 9 tests
```

## Checklist de la entrega — Validación cruzada respetando el tiempo

- [x] **`TimeSeriesSplit` con al menos 5 folds sobre el set de
  entrenamiento**: `evaluate_sales_forecast.time_series_cv()`,
  `N_SPLITS = 5`, sobre `train_features` (84 meses, 2017-2023 — ver
  "Features de lag/rolling" abajo sobre por qué no son 96).
- [x] **Verificación explícita de que ningún fold mezcla o baraja los
  datos**: `time_series_cv()` trae un `assert train_idx.max() < val_idx.min()`
  **en cada fold**, en tiempo de ejecución — no solo confiar en que
  `TimeSeriesSplit` lo garantice. Re-verificado además en
  `tests/pipelines/test_timeseries_cv_order.py` (4 tests): orden dentro de
  cada fold, ventanas de validación avanzando estrictamente entre folds, la
  función de producción real no dispara el assert, y un test que documenta
  que la garantía es *posicional* (si el DataFrame no llega pre-ordenado por
  `month`, `TimeSeriesSplit` no lo notaría — por eso
  `prepare_train_test_features()` siempre entrega filas ordenadas).
- [x] **Sin fuga de información entre los límites de cada fold en las
  features de lag/rolling**: las features (`lag_1`, `lag_12`,
  `rolling_mean_3`, `rolling_std_3`) se calculan **una sola vez**, sobre toda
  la serie ordenada cronológicamente, **antes** de correr la validación
  cruzada (`add_lag_rolling_features()` en `train_sales_forecast.py`, con
  `.shift()` — cada valor depende solo de filas estrictamente anteriores).
  Por construcción, ningún límite de fold puede hacer que una fila "vea" un
  valor calculado con datos de su propia ventana de validación o de una
  posterior — ver el docstring de esa función y de
  `evaluate_sales_forecast.py` para el detalle de por qué esto evita
  exactamente el riesgo que describe la guía ("un feature de lag calculado
  sobre la serie completa antes de dividir puede seguir asomándose a un
  fold futuro si no cuidas dónde empieza la ventana de cada fold" — no pasa
  acá porque el feature nunca mira hacia adelante, sin importar dónde caiga
  la ventana).
- [x] **Métrica reportada como media ± desviación estándar, no un número
  agregado**: `mae_mean_eur`/`mae_std_eur` y `rmse_mean_eur`/`rmse_std_eur`
  en `time_series_cv()`, con la tabla fold-por-fold completa en
  `data/eval/evaluation_report.md`.

## Checklist de la entrega — Curva de aprendizaje

- [x] **Curva de error de entrenamiento y de validación vs. tamaño del set
  de entrenamiento**: `evaluate_sales_forecast.learning_curve_data()` —
  crece el tamaño de entrenamiento tomando prefijos cronológicos cada vez
  más largos (nunca al azar: sería incoherente con una serie de tiempo),
  contra una ventana de validación fija (el último 20% de `train_features`,
  siempre posterior a cualquier prefijo de entrenamiento usado).
- [x] **Imagen guardada en `data/eval/`**:
  [`data/eval/sales-forecast/learning_curve.png`](../data/eval/sales-forecast/learning_curve.png).
  Muestra una brecha persistente entre error de entrenamiento (~15-20K EUR)
  y de validación (~45-50K EUR) que **no se cierra** ni con el set de
  entrenamiento completo — la evidencia visual detrás del diagnóstico de
  sobreajuste (ver abajo).

## Checklist de la entrega — Selección y cálculo de métricas

- [x] **MAE y RMSE para entrenamiento y validación**:
  `in_sample_train_errors()` (entrenamiento, modelo final sobre todo
  `train_features`) + `time_series_cv()` (validación, los 5 folds). Tabla
  completa en `data/eval/evaluation_report.md`.
- [x] **Justificación por escrito de cuál refleja mejor el costo de negocio**:
  sección "Por qué RMSE, no MAE" del reporte — el CONTEXT (Sección 3) pide
  explícitamente que el modelo permita "distinguir con confianza... una
  caída atípica que amerite investigación": ese es un costo de negocio
  sensible a errores *grandes y puntuales*, que RMSE penaliza
  cuadráticamente y MAE no. Copiado también en el docstring de
  `evaluate_sales_forecast.py`.

## Checklist de la entrega — Diagnóstico y reporte técnico

- [x] **Reporte técnico en `data/eval/evaluation_report.md`** que clasifica
  el modelo explícitamente: `diagnose_fit()` da **OVERFITTING** para esta
  corrida —RMSE de validación (46 598 EUR) es 2.07x el de entrenamiento
  (22 517 EUR), por encima del umbral de sobreajuste (1.6x, elegido y
  documentado en el propio script) — respaldado por la tabla de CV fold por
  fold y por la curva de aprendizaje (brecha persistente, no se cierra).
- [x] **Acción correctiva concreta y coherente con el diagnóstico** (no
  genérica): para overfitting, `_corrective_action()` propone **subir
  `min_samples_leaf` y/o bajar `max_depth`** en
  `train_sales_forecast.train_model()` — explícitamente **no** "agregar más
  datos" (no hay más años disponibles: el dataset tiene 10 años fijos) ni
  "aumentar la complejidad" (eso empeoraría el sobreajuste que ya se
  diagnosticó). El mismo `_corrective_action()` también cubre los otros dos
  diagnósticos (underfitting: revisar si `max_depth` es muy bajo o faltan
  features, no reducir complejidad; bien ajustado: sin acción inmediata,
  monitorear PSI) para que el reporte generado siempre sea coherente con lo
  que efectivamente se diagnosticó esa corrida, no un texto fijo.

## Checklist de la entrega — Pruebas

- [x] **Test unitario en `tests/pipelines/` que valida que la validación
  cruzada temporal preserva el orden cronológico**:
  `tests/pipelines/test_timeseries_cv_order.py` (4 tests, ver el detalle en
  el checklist de "Validación cruzada" arriba).

## Decisiones de implementación no cubiertas por la guía genérica

- **Trend model no se re-ajusta por fold** (simplificación documentada en
  el docstring de `evaluate_sales_forecast.py`): la descomposición
  tendencia+residuo (necesaria para que un Random Forest pueda proyectar
  2024-2025, ver `Pasos/sales-forecast-model.md`) usa un `LinearRegression`
  ajustado una sola vez con los 8 años completos de entrenamiento. Los
  folds iniciales de la CV (14-28 meses) tendrían muy poca información para
  reajustar esa tendencia de forma confiable — se trata como una
  transformación de preprocesamiento fija, y la CV evalúa la capacidad del
  Random Forest de generalizar el residuo estacional, no la tendencia en sí.
- **`lag_12` recorta las primeras 12 filas de entrenamiento**: de 96 meses
  de train (2016-2023) quedan 84 (2017-2023) tras el `dropna` por `lag_12`
  en `NaN`. Es el costo directo de pedir un lag de 12 meses con solo 8 años
  de historia — documentado, no oculto (`prepare_train_test_features()` lo
  deja explícito en su docstring).
- **`data/raw/trackflow_sales.csv` real, `us`/`spain` sigue sintético**: ver
  la sección de arriba — es lo que el propio CONTEXT5 (Sección 5) autoriza
  explícitamente para la parte que no viene en los datos reales.

## Pendiente / siguientes pasos

1. Aplicar la acción correctiva propuesta (`min_samples_leaf`/`max_depth`)
   y volver a correr `evaluate_sales_forecast.py` para confirmar que el
   diagnóstico mejora a "bien ajustado" — no se aplicó en esta entrega
   porque el objetivo era la *metodología* de evaluación y diagnóstico en
   sí, no iterar el modelo hasta el mejor resultado posible.
2. Si se reajustan los hiperparámetros, `data/eval/sales-forecast/metrics.json`
   y `prediction_vs_actual.png` (de `train_sales_forecast.py`) también
   deberían regenerarse — hoy reflejan el modelo actual (con
   `min_samples_leaf=2`, `max_depth=6`, diagnosticado overfitting), no uno
   corregido.
3. Reconciliar "K2 Score" (ver `Pasos/sales-forecast-model.md`) sigue
   pendiente — no forma parte de esta entrega de evaluación.
