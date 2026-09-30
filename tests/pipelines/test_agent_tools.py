"""Tests de las tools del agente (`CONTEXT/CONTEXT7.md`, secciones "Tool
obligatoria: consulta de tickets de soporte" y "Tool extra (opcional):
consulta de inventario").

Corren sin red real: `httpx.MockTransport` simula las respuestas del backend
real de `services/incidents-api` (mismos schemas/paths que expone de verdad
-- `GET /api/incidents`, `GET /api/incidents/{id}`, `GET /inventory/products`
-- nunca un dataset paralelo inventado). Mismo patrón que
`tests/pipelines/test_agent_graph.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "services" / "knowledge-api"))

from tools.incidents_tool import (  # noqa: E402
    IncidentQueryInput,
    extract_incident_query,
    query_incidents,
)
from tools.inventory_tool import (  # noqa: E402
    InventoryQueryInput,
    extract_inventory_query,
    query_inventory,
)


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- incidents_tool: extracción de intención desde lenguaje natural ---------


def test_extract_incident_query_finds_numeric_ticket_id():
    query = extract_incident_query("¿cuál es el estado del ticket 42?")
    assert query.incident_id == 42
    assert query.status is None


def test_extract_incident_query_finds_status_keyword_when_no_id():
    query = extract_incident_query("¿qué incidencias siguen abiertos?")
    assert query.incident_id is None
    assert query.status == "open"


def test_extract_incident_query_defaults_to_no_filter():
    query = extract_incident_query("¿cómo van los tickets?")
    assert query.incident_id is None
    assert query.status is None


# --- incidents_tool: lectura real (vía MockTransport) -----------------------


def test_query_incidents_by_id_found():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/incidents/42"
        return httpx.Response(
            200,
            json={
                "id": 42,
                "title": "Paquete perdido",
                "description": "...",
                "status": "open",
                "category": "lost_parcel",
                "origin": "customer",
                "branch": "la_warehouse",
                "source_incident_id": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

    result = query_incidents(IncidentQueryInput(incident_id=42), client=_client_for(handler))

    assert result.ok is True
    assert result.error is None
    assert len(result.incidents) == 1
    assert result.incidents[0].id == 42
    assert result.incidents[0].status == "open"


def test_query_incidents_by_id_not_found_returns_honest_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    result = query_incidents(IncidentQueryInput(incident_id=999), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "not_found"
    assert result.incidents == []


def test_query_incidents_unauthorized_is_reported_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    result = query_incidents(IncidentQueryInput(incident_id=1), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "unauthorized"


def test_query_incidents_list_with_status_filter_forwards_query_params():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/incidents"
        assert dict(request.url.params) == {"status": "open"}
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "title": "A",
                    "description": "",
                    "status": "open",
                    "category": "x",
                    "origin": "customer",
                    "branch": "b1",
                    "source_incident_id": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
        )

    result = query_incidents(IncidentQueryInput(status="open"), client=_client_for(handler))

    assert result.ok is True
    assert len(result.incidents) == 1


def test_query_incidents_timeout_is_a_named_fallback_not_a_hang():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    result = query_incidents(IncidentQueryInput(incident_id=1), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "timeout"


def test_query_incidents_connection_error_is_a_named_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = query_incidents(IncidentQueryInput(incident_id=1), client=_client_for(handler))

    assert result.ok is False
    assert result.error.startswith("connection_error")


def test_incidents_tool_module_has_no_write_capability():
    """La tool es de solo lectura: no debe existir ninguna función que
    pueda crear/actualizar/eliminar tickets, ni siquiera sin usar."""
    import tools.incidents_tool as module

    source = Path(module.__file__).read_text()
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source


# --- inventory_tool ----------------------------------------------------------


def test_extract_inventory_query_finds_sku():
    query = extract_inventory_query("¿cuánto stock queda del SKU CLT-SNK-W-42-Z?")
    assert query.sku == "CLT-SNK-W-42-Z"


def test_extract_inventory_query_defaults_to_no_filter():
    query = extract_inventory_query("¿cómo está el inventario en general?")
    assert query.sku is None


def test_query_inventory_lists_full_catalog_when_no_sku_requested():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/inventory/products"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "Zapatilla",
                    "sku": "CLT-SNK-W-42-Z",
                    "client_name": "Cliente A",
                    "category": "footwear",
                    "warehouse": "la_warehouse",
                    "current_stock": 12,
                },
                {
                    "id": 2,
                    "name": "Remera",
                    "sku": "CLT-SHT-M-10-A",
                    "client_name": "Cliente B",
                    "category": "apparel",
                    "warehouse": "sf_warehouse",
                    "current_stock": 3,
                },
            ],
        )

    result = query_inventory(InventoryQueryInput(sku=None), client=_client_for(handler))

    assert result.ok is True
    assert len(result.products) == 2


def test_query_inventory_filters_client_side_by_sku():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "Zapatilla",
                    "sku": "CLT-SNK-W-42-Z",
                    "client_name": "Cliente A",
                    "category": "footwear",
                    "warehouse": "la_warehouse",
                    "current_stock": 12,
                },
                {
                    "id": 2,
                    "name": "Remera",
                    "sku": "CLT-SHT-M-10-A",
                    "client_name": "Cliente B",
                    "category": "apparel",
                    "warehouse": "sf_warehouse",
                    "current_stock": 3,
                },
            ],
        )

    result = query_inventory(InventoryQueryInput(sku="CLT-SHT-M-10-A"), client=_client_for(handler))

    assert result.ok is True
    assert len(result.products) == 1
    assert result.products[0].sku == "CLT-SHT-M-10-A"


def test_query_inventory_sku_not_in_catalog_is_an_honest_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    result = query_inventory(InventoryQueryInput(sku="DOES-NOT-EXIST-1"), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "not_found"


def test_query_inventory_timeout_is_a_named_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    result = query_inventory(InventoryQueryInput(sku=None), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "timeout"


def test_inventory_tool_module_has_no_write_capability():
    import tools.inventory_tool as module

    source = Path(module.__file__).read_text()
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source
