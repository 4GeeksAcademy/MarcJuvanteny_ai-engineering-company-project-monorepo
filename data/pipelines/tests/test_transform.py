"""Tests de las funciones puras de transform.py (sin DB, sin Prefect)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exec_weekly_inventory_kpis.transform import (
    build_weekly_kpis,
    enrich_with_sku,
    iso_week_of,
    normalize_events,
    pair_receipt_dispatch,
)

WEEK_START = datetime(2026, 8, 24, tzinfo=timezone.utc)  # lunes ISO 2026-W35
WEEK_END = WEEK_START + timedelta(days=7)


def _raw_event(event_id, event_type, ts, warehouse="LA", client_id="Acme", product_id="SKU-1", quantity=10):
    return {
        "event_id": event_id,
        "timestamp": ts,
        "session_id": "s1",
        "user_id": "u1",
        "event_type": event_type,
        "schema_version": "1.0",
        "request_id": "r1",
        "properties": {
            "warehouse": warehouse,
            "client_id": client_id,
            "product_id": product_id,
            "product_category": "fashion",
            "quantity": quantity,
        },
    }


def test_normalize_events_flattens_properties_and_dedupes():
    events = pd.DataFrame(
        [
            _raw_event("e1", "inbound_order_created", WEEK_START + timedelta(hours=1)),
            _raw_event("e1", "inbound_order_created", WEEK_START + timedelta(hours=1)),  # duplicado exacto
        ]
    )
    clean, qc = normalize_events(events)

    assert len(clean) == 1
    assert clean.iloc[0]["warehouse"] == "LA"
    assert qc["rows_read"] == 2
    assert qc["rows_rejected"] == 0


def test_normalize_events_rejects_missing_required_field():
    event = _raw_event("e2", "inbound_order_created", WEEK_START + timedelta(hours=1))
    del event["properties"]["client_id"]
    clean, qc = normalize_events(pd.DataFrame([event]))

    assert clean.empty
    assert qc["rows_rejected"] == 1
    assert qc["error_sample"][0]["missing_field"] == "client_id"


def test_normalize_events_maps_spec_warehouse_names_to_real_values():
    event = _raw_event("e3", "inbound_order_created", WEEK_START + timedelta(hours=1))
    event["properties"]["warehouse"] = "los_angeles"
    clean, _ = normalize_events(pd.DataFrame([event]))

    assert clean.iloc[0]["warehouse"] == "LA"


def test_pair_receipt_dispatch_matches_first_outbound_after_inbound():
    events = pd.DataFrame(
        [
            _raw_event("e1", "inbound_order_created", WEEK_START + timedelta(hours=1)),
            _raw_event("e2", "outbound_order_created", WEEK_START + timedelta(hours=25)),  # +24h -> cycle time
            _raw_event("e3", "outbound_order_created", WEEK_START + timedelta(hours=50)),  # posterior, no debe emparejarse
        ]
    )
    clean, _ = normalize_events(events)
    pairs = pair_receipt_dispatch(clean)

    assert len(pairs) == 1
    assert pairs.iloc[0]["cycle_time_h"] == pytest.approx(24.0)


def test_pair_receipt_dispatch_ignores_outbound_before_inbound():
    events = pd.DataFrame(
        [
            _raw_event("e1", "outbound_order_created", WEEK_START + timedelta(hours=1)),
            _raw_event("e2", "inbound_order_created", WEEK_START + timedelta(hours=5)),
        ]
    )
    clean, _ = normalize_events(events)
    pairs = pair_receipt_dispatch(clean)

    assert pairs.empty


def test_enrich_with_sku_counts_unmatched_product_id():
    events = pd.DataFrame(
        [
            _raw_event("e1", "inbound_order_created", WEEK_START + timedelta(hours=1), product_id="SKU-1"),
            _raw_event("e2", "inbound_order_created", WEEK_START + timedelta(hours=1), product_id="SKU-GHOST"),
        ]
    )
    clean, _ = normalize_events(events)
    sku_df = pd.DataFrame([{"id": 1, "name": "Shoe", "sku": "SKU-1", "client_name": "Acme", "category": "fashion", "warehouse": "LA"}])

    enriched, rows_unmatched_sku = enrich_with_sku(clean, sku_df)

    assert rows_unmatched_sku == 1
    assert enriched.loc[enriched["product_id"] == "SKU-1", "sku_id"].iloc[0] == 1


def test_iso_week_of_matches_expected_week():
    assert iso_week_of(WEEK_START) == "2026-W35"


def test_build_weekly_kpis_computes_fulfillment_and_discrepancy_rate():
    events = [
        _raw_event("e1", "outbound_order_created", WEEK_START + timedelta(hours=1), quantity=90),
        _raw_event("e2", "stock_threshold_triggered", WEEK_START + timedelta(hours=2), quantity=10),
        _raw_event("e3", "inbound_order_created", WEEK_START + timedelta(hours=3), quantity=100),
        _raw_event("e4", "inventory_discrepancy_detected", WEEK_START + timedelta(hours=4), quantity=1),
    ]
    events_df = pd.DataFrame(events)
    sku_df = pd.DataFrame([{"id": 1, "name": "Shoe", "sku": "SKU-1", "client_name": "Acme", "category": "fashion", "warehouse": "LA"}])

    kpis_df, qc = build_weekly_kpis(events_df, sku_df, WEEK_START, WEEK_END)

    assert len(kpis_df) == 1
    row = kpis_df.iloc[0]
    assert row["iso_week"] == "2026-W35"
    # fulfillment_rate = outbound_qty / (outbound_qty + stock_threshold_qty) = 90 / (90 + 10)
    assert row["fulfillment_rate"] == pytest.approx(0.9)
    # discrepancy_frequency = discrepancies / (inbound_orders + outbound_orders) * 1000 = 1 / 2 * 1000
    assert row["discrepancy_frequency"] == pytest.approx(500.0)
    assert qc["rows_transformed"] == 1
    assert qc["rows_unmatched_sku"] == 0


def test_build_weekly_kpis_empty_input_returns_empty_frame():
    kpis_df, qc = build_weekly_kpis(pd.DataFrame(), pd.DataFrame(), WEEK_START, WEEK_END)

    assert kpis_df.empty
    assert qc["rows_read"] == 0
