"""Modelos Pydantic de request/response (Fase 5.1 del diseno).

La forma de `WeeklyInventoryKpiRow` sigue el esquema de
`reporting.exec_weekly_inventory_kpis` (diseno, Fase 2.5) al ser el mismo
contrato que consumiria un `CONTEXT-company.md` real si existiera en el repo
(ver la nota al respecto en `Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md`).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    pipeline_name: str | None = None
    pipeline_version: str | None = None
    trigger: str | None = None
    iso_week: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    rows_read: int | None = None
    rows_rejected: int | None = None
    rows_unmatched_sku: int | None = None
    error_message: str | None = None


class RunTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iso_week: str | None = None


class RunTriggerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    iso_week: str
    status: str = "running"


class WeeklyInventoryKpiRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iso_week: str
    week_start: datetime
    week_end: datetime
    warehouse: str
    country: str | None = None
    client_id: str
    inbound_orders: int
    outbound_orders: int
    inbound_qty: float
    outbound_qty: float
    stock_threshold_events: int
    discrepancy_events: int
    governance_flags: int
    fulfillment_rate: float | None = None
    discrepancy_frequency: float | None = None
    receipt_to_dispatch_cycle_time_h: float | None = None
    events_considered: int
    pipeline_run_id: str
    computed_at: datetime
