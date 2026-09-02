"""Configuracion y constantes del pipeline exec_weekly_inventory_kpis.

Ninguna credencial vive aqui: solo nombres, defaults y el vocabulario de
dominio fijado en Pasos/telemetria-diseno-pipeline-reporting-ejecutivo.md
(Fase 2). blocks.py resuelve la conexion real (Prefect block o env var).
"""

from __future__ import annotations

PIPELINE_NAME = "exec_weekly_inventory_kpis"
PIPELINE_VERSION = "0.1.0"

# Los 5 event_type de inventario definidos como obligatorios en
# CONTEXT-trackflow.md Sec.3. Unica fuente de verdad para extract/transform.
INVENTORY_EVENT_TYPES = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "inventory_discrepancy_detected",
    "direct_stock_edit_rejected",
)

# warehouse -> country, segun models.py VALID_COUNTRIES y CONTEXT.md.
WAREHOUSE_COUNTRY_MAP = {"LA": "USA", "ZGZ": "Spain"}

# Campos minimos que properties debe traer para que un evento de inventario
# sea utilizable (ver transform.normalize_events).
REQUIRED_EVENT_PROPERTIES = (
    "warehouse",
    "client_id",
    "product_id",
    "product_category",
)

# reporting-pipeline-config (Fase 4.2 del diseno): parametros no secretos,
# versionables sin tocar codigo. blocks.get_pipeline_config() los carga desde
# un Prefect JSON/Variable block si existe, si no usa estos defaults.
DEFAULT_PIPELINE_CONFIG = {
    "grace_window_days": 7,
    "error_sample_size": 20,
    "timezone": "UTC",
    "week_scheme": "iso",
    "low_stock_threshold": 10,
}

# Esquema/tablas de destino (Fase 2.5 / 3.2 del diseno). schema="" (usado en
# tests con SQLite) genera nombres de tabla planos sin prefijo de esquema.
REPORTING_SCHEMA = "reporting"
FACT_TABLE = "exec_weekly_inventory_kpis"
STAGING_TABLE = "_stg_exec_weekly_inventory_kpis"
DIM_SKU_TABLE = "dim_sku"
RUNS_TABLE = "pipeline_runs"

# data/eval/ es el destino del snapshot opcional (paso no critico, Fase 1 del
# Hito de implementacion): un volcado legible del resultado de cada corrida
# para validacion manual, separado del dato materializado en Postgres.
EVAL_SNAPSHOT_SUBDIR = "exec-weekly-inventory-kpis"


def qualified_table(table: str, schema: str = REPORTING_SCHEMA) -> str:
    """Nombre de tabla cualificado por esquema (o plano si schema="")."""
    return f"{schema}.{table}" if schema else table
