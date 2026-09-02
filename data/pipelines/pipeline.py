"""Punto de entrada principal de data/pipelines/.

Ejecucion manual (semana ISO ya cerrada mas reciente):

    uv run data/pipelines/pipeline.py

Semana concreta:

    uv run data/pipelines/pipeline.py --iso-week 2026-W35

Backfill de un rango de semanas:

    uv run data/pipelines/pipeline.py --from-week 2026-W30 --to-week 2026-W35

El flow y las tasks viven en `exec_weekly_inventory_kpis/` (ver ese paquete y
Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md para el diseno);
este script solo expone la CLI y sirve como deployment entrypoint de Prefect.
"""

from __future__ import annotations

import argparse

from exec_weekly_inventory_kpis import exec_weekly_inventory_kpis_backfill_flow, exec_weekly_inventory_kpis_flow


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso-week", default=None, help='Semana ISO a procesar, p. ej. "2026-W35". Por defecto: la ultima semana cerrada.')
    parser.add_argument("--from-week", default=None, help="Inicio del rango para un backfill (requiere --to-week).")
    parser.add_argument("--to-week", default=None, help="Fin del rango para un backfill (requiere --from-week).")
    parser.add_argument(
        "--trigger",
        default="manual",
        choices=["scheduled", "manual", "backfill"],
        help="Como queda registrada la corrida en reporting.pipeline_runs (default: manual, para ejecucion por CLI).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.from_week or args.to_week:
        if not (args.from_week and args.to_week):
            raise SystemExit("--from-week y --to-week deben usarse juntos.")
        results = exec_weekly_inventory_kpis_backfill_flow(from_week=args.from_week, to_week=args.to_week)
        for result in results:
            print(result)
        return

    result = exec_weekly_inventory_kpis_flow(iso_week=args.iso_week, trigger=args.trigger)
    print(result)


if __name__ == "__main__":
    main()
