# Reporte técnico de evaluación — modelo de predicción de ingresos TrackFlow

Generado por `scripts/evaluate_sales_forecast.py`. Ver `Pasos/sales-forecast-evaluation.md`
para el detalle completo de la metodología.

## Validación cruzada temporal (5 folds, `TimeSeriesSplit`)

| Fold | Meses train | Meses validación | MAE (EUR) | RMSE (EUR) |
| --- | --- | --- | --- | --- |
| 1 | 14 | 14 | 51953 | 55429 |
| 2 | 28 | 14 | 38324 | 48778 |
| 3 | 42 | 14 | 26263 | 32281 |
| 4 | 56 | 14 | 43854 | 49329 |
| 5 | 70 | 14 | 37923 | 47171 |

- **MAE validación**: 39663 ± 8402 EUR (media ± desvío estándar entre folds).
- **RMSE validación**: 46598 ± 7688 EUR.
- **RMSE entrenamiento** (in-sample, modelo final): 22517 EUR.

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

## Diagnóstico: **OVERFITTING**

- RMSE entrenamiento: 22517 EUR.
- RMSE validación: 46598 ± 7688 EUR.
- Razón validación/entrenamiento: 2.07x (umbral de sobreajuste: >1.6x).
- RMSE de validación como % del ingreso mensual promedio: 4.65% (umbral de underfitting: >12.0%).

Ver `data/eval/sales-forecast/learning_curve.png`: el gap entre error de entrenamiento y de validación es visible incluso con el set de entrenamiento completo.

## Acción correctiva propuesta

El Random Forest memoriza ruido de train que no generaliza (gap grande entre error de entrenamiento y de validación). Acción concreta: reducir la complejidad del bosque -- subir `min_samples_leaf` (hoy 2) y/o bajar `max_depth` (hoy 6) en `train_sales_forecast.train_model()` -- antes que agregar más datos (no hay más años disponibles) o más features (ya se agregaron lag/rolling; agregar más solo empeoraría el sobreajuste con 84 filas de entrenamiento).
