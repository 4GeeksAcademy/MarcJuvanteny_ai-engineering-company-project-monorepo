"""Los tres endpoints de `services/reporting/` (Fase 5.1 del diseno).

Capa HTTP fina: valida query/body, llama a `data/pipelines/exec_weekly_inventory_kpis`
(flow + queries de solo lectura) y serializa la respuesta. Ninguna logica de
ETL vive aqui (Fase 5.2, regla transversal) — si un endpoint necesitara un
calculo nuevo, ese calculo se agrega como funcion de transformacion en
`data/pipelines/.../transform.py`, no en este router.
"""

from __future__ import annotations

import pipeline_path  # noqa: F401  (efecto secundario: agrega data/pipelines/ a sys.path)
from auth import Principal, get_current_principal, require_manual_trigger_role
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from schemas import RunStatusResponse, RunTriggerRequest, RunTriggerResponse, WeeklyInventoryKpiRow

from exec_weekly_inventory_kpis import flow as pipeline_flow
from exec_weekly_inventory_kpis import load as pipeline_load
from exec_weekly_inventory_kpis import queries as pipeline_queries
from exec_weekly_inventory_kpis.blocks import get_engine
from exec_weekly_inventory_kpis.config import PIPELINE_NAME

router = APIRouter(prefix="/reporting/exec-weekly", tags=["reporting"])


@router.get("/status", response_model=RunStatusResponse)
def get_status(_: Principal = Depends(get_current_principal)) -> RunStatusResponse:
    """Ultima corrida del pipeline: para el panel de operacion / health-check
    del dashboard ejecutivo (diseno, Fase 5.1)."""
    engine = get_engine()
    latest_run = pipeline_queries.read_latest_run(engine, pipeline_name=PIPELINE_NAME)
    if latest_run is None:
        return RunStatusResponse()
    known_fields = {field: latest_run.get(field) for field in RunStatusResponse.model_fields if field in latest_run}
    return RunStatusResponse(**known_fields)


@router.post("/run", response_model=RunTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_run(
    payload: RunTriggerRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(require_manual_trigger_role),
) -> RunTriggerResponse:
    """Disparo manual: abre la fila de `pipeline_runs` de forma sincrona (para
    devolver `run_id` ya mismo) y lanza el flow completo en background — el
    request nunca ejecuta ETL en el proceso web (diseno, Fase 5.1)."""
    engine = get_engine()
    pipeline_load.ensure_schema(engine)
    extract_start, _week_start, week_end, resolved_iso_week = pipeline_flow.resolve_extraction_window(payload.iso_week)

    run_id = pipeline_load.open_run(
        engine,
        trigger="manual",
        triggered_by=str(principal.user_id),
        window_from=extract_start,
        window_to=week_end,
        iso_week=resolved_iso_week,
    )

    background_tasks.add_task(
        pipeline_flow.exec_weekly_inventory_kpis_flow,
        iso_week=resolved_iso_week,
        trigger="manual",
        run_id=run_id,
    )

    return RunTriggerResponse(run_id=run_id, iso_week=resolved_iso_week)


@router.get("/kpis", response_model=list[WeeklyInventoryKpiRow])
def get_kpis(
    from_week: str = Query(..., description="Semana ISO inicial, p.ej. 2026-W30"),
    to_week: str = Query(..., description="Semana ISO final, p.ej. 2026-W35"),
    warehouse: str | None = Query(None, description="LA | ZGZ"),
    country: str | None = Query(None, description="USA | Spain"),
    client_id: str | None = Query(None, description="Nombre de marca (SKU.client_name)"),
    _: Principal = Depends(get_current_principal),
) -> list[WeeklyInventoryKpiRow]:
    """Feed que consume el dashboard ejecutivo. Solo lectura: nunca recalcula
    ni lee `telemetry_events` (diseno, Fase 5.1)."""
    engine = get_engine()
    kpis_df = pipeline_queries.query_weekly_kpis(
        engine, from_week, to_week, warehouse=warehouse, country=country, client_id=client_id
    )
    return [WeeklyInventoryKpiRow(**row) for row in kpis_df.to_dict(orient="records")]
