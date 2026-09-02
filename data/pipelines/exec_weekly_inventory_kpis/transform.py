"""Transformacion (Fase 2 / 3.1.4 del diseno): funciones puras, sin I/O.

Ninguna funcion de este modulo abre conexion ni muta sus argumentos: dado el
mismo `events_df`/`sku_df`/ventana, siempre produce el mismo resultado. Eso es
lo que permite reintentar la carga sin reintentar la transformacion (Fase 4.1:
`build_weekly_kpis` tiene 0 retries porque un fallo aqui es un bug, no un
problema transitorio).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .config import REQUIRED_EVENT_PROPERTIES, WAREHOUSE_COUNTRY_MAP

EMPTY_KPI_COLUMNS = (
    "iso_week",
    "week_start",
    "week_end",
    "warehouse",
    "country",
    "client_id",
    "inbound_orders",
    "outbound_orders",
    "inbound_qty",
    "outbound_qty",
    "stock_threshold_events",
    "discrepancy_events",
    "governance_flags",
    "fulfillment_rate",
    "discrepancy_frequency",
    "receipt_to_dispatch_cycle_time_h",
    "events_considered",
)


def normalize_events(events_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """JSONB `properties` -> columnas, dedupe por event_id, valida campos minimos.

    Devuelve `(clean_df, qc)` donde `qc` trae `rows_read`, `rows_rejected` y
    `error_sample` (hasta 20 ejemplos anonimizados: event_id/event_type/campo
    ausente) para `reporting.pipeline_runs` (Fase 3.2).
    """
    rows_read = len(events_df)
    if events_df.empty:
        return events_df.assign(**{col: pd.Series(dtype="object") for col in REQUIRED_EVENT_PROPERTIES}), {
            "rows_read": 0,
            "rows_rejected": 0,
            "error_sample": [],
        }

    deduped = events_df.drop_duplicates(subset=["event_id"]).copy()
    properties = pd.json_normalize(deduped["properties"])
    normalized = pd.concat([deduped.reset_index(drop=True), properties.reset_index(drop=True)], axis=1)

    if "warehouse" in normalized.columns:
        normalized["warehouse"] = normalized["warehouse"].replace(
            {"los_angeles": "LA", "zaragoza": "ZGZ"}
        )

    missing_mask = pd.Series(False, index=normalized.index)
    for field in REQUIRED_EVENT_PROPERTIES:
        if field not in normalized.columns:
            normalized[field] = None
        missing_mask = missing_mask | normalized[field].isna()

    error_sample = [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "missing_field": next(f for f in REQUIRED_EVENT_PROPERTIES if pd.isna(row[f])),
        }
        for _, row in normalized.loc[missing_mask].head(20).iterrows()
    ]

    clean = normalized.loc[~missing_mask].copy()
    if "quantity" in clean.columns:
        clean["quantity"] = pd.to_numeric(clean["quantity"], errors="coerce").fillna(0)
    else:
        clean["quantity"] = 0

    qc = {
        "rows_read": rows_read,
        "rows_rejected": int(missing_mask.sum()),
        "error_sample": error_sample,
    }
    return clean, qc


def derive_country(events_df: pd.DataFrame) -> pd.DataFrame:
    """Anade `country` derivado de `warehouse` (LA->USA, ZGZ->Spain)."""
    if events_df.empty:
        return events_df.assign(country=pd.Series(dtype="object"))
    result = events_df.copy()
    result["country"] = result["warehouse"].map(WAREHOUSE_COUNTRY_MAP)
    return result


def enrich_with_sku(events_df: pd.DataFrame, sku_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Join `properties.product_id` <-> `SKU.sku`. Devuelve `(enriched_df, rows_unmatched_sku)`."""
    if events_df.empty:
        return events_df.assign(sku_id=pd.Series(dtype="Int64")), 0

    sku_lookup = sku_df.rename(columns={"id": "sku_id", "category": "sku_category", "name": "sku_name"})
    enriched = events_df.merge(
        sku_lookup[["sku_id", "sku", "sku_category", "sku_name"]],
        left_on="product_id",
        right_on="sku",
        how="left",
    )
    rows_unmatched_sku = int(enriched["sku_id"].isna().sum())
    return enriched, rows_unmatched_sku


def pair_receipt_dispatch(events_df: pd.DataFrame) -> pd.DataFrame:
    """Empareja cada `inbound_order_created` con el primer `outbound_order_created`
    posterior del mismo `(warehouse, client_id, product_id)`.

    Devuelve un DataFrame con una fila por par emparejado y su
    `cycle_time_h` (horas), agrupable luego por `(iso_week, warehouse, client_id)`
    usando la semana del outbound (el evento que cierra el ciclo).
    """
    columns = ["warehouse", "client_id", "iso_week", "cycle_time_h"]
    if events_df.empty:
        return pd.DataFrame(columns=columns)

    inbound = events_df.loc[events_df["event_type"] == "inbound_order_created"].sort_values("timestamp")
    outbound = events_df.loc[events_df["event_type"] == "outbound_order_created"].sort_values("timestamp")
    if inbound.empty or outbound.empty:
        return pd.DataFrame(columns=columns)

    pairs: list[dict[str, Any]] = []
    for key, inbound_group in inbound.groupby(["warehouse", "client_id", "product_id"]):
        outbound_group = outbound.loc[
            (outbound["warehouse"] == key[0])
            & (outbound["client_id"] == key[1])
            & (outbound["product_id"] == key[2])
        ]
        if outbound_group.empty:
            continue
        available_outbound = outbound_group["timestamp"].to_numpy()
        for _, inbound_row in inbound_group.iterrows():
            later = outbound_group.loc[outbound_group["timestamp"] > inbound_row["timestamp"]]
            if later.empty:
                continue
            match = later.iloc[0]
            cycle_time_h = (match["timestamp"] - inbound_row["timestamp"]).total_seconds() / 3600
            pairs.append(
                {
                    "warehouse": key[0],
                    "client_id": key[1],
                    "iso_week": iso_week_of(match["timestamp"]),
                    "cycle_time_h": cycle_time_h,
                }
            )
    return pd.DataFrame(pairs, columns=columns)


def iso_week_of(timestamp: pd.Timestamp) -> str:
    iso_calendar = pd.Timestamp(timestamp).isocalendar()
    return f"{iso_calendar.year}-W{iso_calendar.week:02d}"


def aggregate_weekly_kpis(
    events_df: pd.DataFrame,
    pairs_df: pd.DataFrame,
    week_start: datetime,
    week_end: datetime,
) -> pd.DataFrame:
    """Agrega por `(iso_week, warehouse, client_id)` los 3 KPIs (Fase 2.1)."""
    if events_df.empty:
        return pd.DataFrame(columns=EMPTY_KPI_COLUMNS)

    grouped = events_df.copy()
    grouped["iso_week"] = grouped["timestamp"].apply(iso_week_of)
    group_keys = ["iso_week", "warehouse", "client_id"]

    def _agg(event_type: str, column: str, func: str) -> pd.Series:
        subset = grouped.loc[grouped["event_type"] == event_type]
        if subset.empty:
            return pd.Series(dtype="float64", index=pd.MultiIndex.from_tuples([], names=group_keys))
        return subset.groupby(group_keys)[column].agg(func)

    events_considered = grouped.groupby(group_keys).size().rename("events_considered")
    inbound_orders = _agg("inbound_order_created", "event_id", "count").rename("inbound_orders")
    outbound_orders = _agg("outbound_order_created", "event_id", "count").rename("outbound_orders")
    inbound_qty = _agg("inbound_order_created", "quantity", "sum").rename("inbound_qty")
    outbound_qty = _agg("outbound_order_created", "quantity", "sum").rename("outbound_qty")
    stock_threshold_events = _agg("stock_threshold_triggered", "event_id", "count").rename(
        "stock_threshold_events"
    )
    stock_threshold_penalty_qty = _agg("stock_threshold_triggered", "quantity", "sum").rename(
        "stock_threshold_penalty_qty"
    )
    discrepancy_events = _agg("inventory_discrepancy_detected", "event_id", "count").rename(
        "discrepancy_events"
    )
    governance_flags = _agg("direct_stock_edit_rejected", "event_id", "count").rename("governance_flags")

    # events_considered cubre todos los event_type, por lo que su indice es
    # superset de cada Series individual: el concat no crea filas nuevas.
    result = (
        pd.concat(
            [
                events_considered,
                inbound_orders,
                outbound_orders,
                inbound_qty,
                outbound_qty,
                stock_threshold_events,
                stock_threshold_penalty_qty,
                discrepancy_events,
                governance_flags,
            ],
            axis=1,
        )
        .fillna(0)
        .reset_index()
    )

    for column in (
        "inbound_orders",
        "outbound_orders",
        "stock_threshold_events",
        "discrepancy_events",
        "governance_flags",
        "events_considered",
    ):
        result[column] = result[column].astype(int)

    fulfilled_denominator = result["outbound_qty"] + result["stock_threshold_penalty_qty"]
    result["fulfillment_rate"] = (result["outbound_qty"] / fulfilled_denominator).where(
        fulfilled_denominator > 0
    )

    movements = result["inbound_orders"] + result["outbound_orders"]
    result["discrepancy_frequency"] = (result["discrepancy_events"] / movements * 1000).where(movements > 0)

    if not pairs_df.empty:
        cycle_time = pairs_df.groupby(group_keys)["cycle_time_h"].median().rename(
            "receipt_to_dispatch_cycle_time_h"
        )
        result = result.merge(cycle_time, on=group_keys, how="left")
    else:
        result["receipt_to_dispatch_cycle_time_h"] = pd.NA

    result["week_start"] = week_start
    result["week_end"] = week_end
    result["country"] = result["warehouse"].map(WAREHOUSE_COUNTRY_MAP)
    result = result.drop(columns=["stock_threshold_penalty_qty"])

    return result[list(EMPTY_KPI_COLUMNS)]


def build_weekly_kpis(
    events_df: pd.DataFrame,
    sku_df: pd.DataFrame,
    week_start: datetime,
    week_end: datetime,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Orquesta normalize -> enrich -> pair -> aggregate. Funcion pura (sin I/O)."""
    clean_events, qc = normalize_events(events_df)
    enriched_events, rows_unmatched_sku = enrich_with_sku(clean_events, sku_df)
    pairs_df = pair_receipt_dispatch(enriched_events)
    kpis_df = aggregate_weekly_kpis(enriched_events, pairs_df, week_start, week_end)
    qc["rows_unmatched_sku"] = rows_unmatched_sku
    qc["rows_transformed"] = len(kpis_df)
    return kpis_df, qc
