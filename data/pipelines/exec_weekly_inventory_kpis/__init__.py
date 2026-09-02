"""Pipeline exec_weekly_inventory_kpis.

Ver Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md para el diseno
completo (Fases 1-5) y Pasos/telemetria-pipeline-implementacion.md para el
registro de esta implementacion.
"""

from .flow import exec_weekly_inventory_kpis_backfill_flow, exec_weekly_inventory_kpis_flow

__all__ = ["exec_weekly_inventory_kpis_flow", "exec_weekly_inventory_kpis_backfill_flow"]
