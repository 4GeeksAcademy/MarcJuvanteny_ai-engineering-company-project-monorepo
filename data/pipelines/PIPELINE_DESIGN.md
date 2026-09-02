# `data/pipelines/` — diseño e implementación

Este archivo es el puntero corto que pide la guía del Hito de Data Pipelines.
El diseño completo (Fases 1–5: análisis, arquitectura, resiliencia,
mapeo a Prefect, integración con la app) vive en
[`Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md`](../../Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md),
y el registro de la implementación (qué se construyó, cómo se probó, qué
falta) en
[`Pasos/telemetria-pipeline-implementacion.md`](../../Pasos/telemetria-pipeline-implementacion.md).

## Pipeline: `exec_weekly_inventory_kpis`

Produce `reporting.exec_weekly_inventory_kpis`: el consolidado semanal de
inventario (`fulfillment_rate`, `discrepancy_frequency`,
`receipt_to_dispatch_cycle_time_h`) por `warehouse` / `client_id` / país que
alimenta el informe ejecutivo del CEO.

## Frecuencia de reporting

**Semanal.** La corrida programada procesa la última semana ISO ya cerrada
(lunes 00:00 UTC → lunes siguiente 00:00 UTC) y se dispara el lunes, una vez
que esa semana terminó. Cada corrida reprocesa también la semana anterior
(ventana de gracia de 7 días) para absorber eventos que llegaron tarde, sin
duplicar filas (UPSERT por `(iso_week, warehouse, client_id)`). Detalle
completo: diseño, Fase 2.2 y 2.4.

Hoy esto reemplaza el ensamblado manual que los directores hacían cada
domingo (`memory-bank/projectbrief.md`).

## Cómo se ejecuta

```bash
cd data/pipelines
uv add "prefect>=3"          # una sola vez, para instalar dependencias

# Última semana ISO cerrada (caso normal, cadencia semanal):
uv run pipeline.py

# Semana concreta:
uv run pipeline.py --iso-week 2026-W35

# Backfill de un rango de semanas:
uv run pipeline.py --from-week 2026-W30 --to-week 2026-W35
```

`pipeline.py` es el entrypoint (`if __name__ == "__main__"`, ver
[`pipeline.py`](./pipeline.py)) tanto para ejecución manual por CLI como para
un deployment de Prefect (`prefect deploy` apuntando a este archivo, pendiente
de configurar — ver "Pendiente" en el documento de implementación).

`POST /reporting/exec-weekly/run` (`services/reporting/`, Fase 5) dispara la
misma lógica de forma manual desde la app, sin pasar por la CLI.
