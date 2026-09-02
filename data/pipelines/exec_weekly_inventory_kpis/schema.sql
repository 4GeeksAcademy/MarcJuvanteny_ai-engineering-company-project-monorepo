-- DDL de reporting.* para exec_weekly_inventory_kpis (Fase 2.5 / 3.1 / 3.2 del
-- diseno: Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md).
--
-- Referencia para desplegar con `psql -f schema.sql` o una migracion.
-- `load.ensure_schema()` crea el mismo esquema en runtime via SQLAlchemy Core
-- (schema.py), portable entre Postgres y SQLite para tests; este archivo es
-- el DDL Postgres idiomatico y documentado.

CREATE SCHEMA IF NOT EXISTS reporting;

-- Tabla de hechos: un registro por (iso_week, warehouse, client_id).
CREATE TABLE IF NOT EXISTS reporting.exec_weekly_inventory_kpis (
    iso_week                          text NOT NULL,
    warehouse                         text NOT NULL,
    client_id                         text NOT NULL,
    week_start                        timestamptz NOT NULL,
    week_end                          timestamptz NOT NULL,
    country                           text,
    inbound_orders                    integer NOT NULL DEFAULT 0,
    outbound_orders                   integer NOT NULL DEFAULT 0,
    inbound_qty                       numeric NOT NULL DEFAULT 0,
    outbound_qty                      numeric NOT NULL DEFAULT 0,
    stock_threshold_events            integer NOT NULL DEFAULT 0,
    discrepancy_events                integer NOT NULL DEFAULT 0,
    governance_flags                  integer NOT NULL DEFAULT 0,
    fulfillment_rate                  numeric(5, 4),
    discrepancy_frequency             numeric,
    receipt_to_dispatch_cycle_time_h  numeric,
    events_considered                 integer NOT NULL DEFAULT 0,
    pipeline_run_id                   uuid NOT NULL,
    computed_at                       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (iso_week, warehouse, client_id)
);

-- Staging desechable: se trunca y rellena por completo en cada corrida
-- (load.stage_kpis), nunca se escribe directo a la tabla final.
CREATE TABLE IF NOT EXISTS reporting._stg_exec_weekly_inventory_kpis (
    LIKE reporting.exec_weekly_inventory_kpis INCLUDING DEFAULTS
);

-- Dimension SKU reconciliada por sku_id (= SKU.id en la BD de dominio).
-- SKU no tiene updated_at, asi que cada corrida hace un snapshot completo y
-- este UPSERT + is_current detecta ediciones/borrados sin perder historico.
CREATE TABLE IF NOT EXISTS reporting.dim_sku (
    sku_id       integer PRIMARY KEY,
    sku          text NOT NULL,
    name         text,
    client_name  text,
    category     text,
    warehouse    text,
    is_current   boolean NOT NULL DEFAULT true,
    seen_at      timestamptz NOT NULL DEFAULT now()
);

-- Log de ejecucion: una fila por corrida. Ver Fase 3.2 del diseno para la
-- justificacion de cada campo.
CREATE TABLE IF NOT EXISTS reporting.pipeline_runs (
    run_id                 uuid PRIMARY KEY,
    pipeline_name          text NOT NULL,
    pipeline_version       text NOT NULL,
    trigger                text NOT NULL,
    triggered_by           text,
    window_from            timestamptz NOT NULL,
    window_to              timestamptz NOT NULL,
    iso_week                text NOT NULL,
    sku_snapshot_rows      integer,
    sku_rows_deactivated   integer,
    started_at             timestamptz NOT NULL,
    finished_at            timestamptz,
    status                 text NOT NULL,
    rows_read              integer,
    rows_rejected          integer,
    rows_unmatched_sku     integer,
    rows_transformed       integer,
    rows_upserted_insert   integer,
    rows_upserted_update   integer,
    error_count            integer,
    error_message          text,
    error_sample           jsonb
);

CREATE INDEX IF NOT EXISTS ix_pipeline_runs_pipeline_started
    ON reporting.pipeline_runs (pipeline_name, started_at DESC);
