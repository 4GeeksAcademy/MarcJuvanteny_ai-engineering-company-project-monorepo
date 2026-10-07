"""Tests de `tools/inventory_tools.py` (tool extra, solo lectura) --
checklist "cualquier intento de modificacion debe ser rechazado
explicitamente por el servidor, no simplemente omitido"."""

from __future__ import annotations

from pathlib import Path

import httpx

from tools.inventory_tools import (
    READ_ONLY_REJECTION_ERROR,
    QueryInventoryInput,
    UpdateInventoryStockInput,
    query_inventory,
    update_inventory_stock,
)

_CATALOG = [
    {
        "id": 1,
        "name": "Zapatilla blanca clasica - Talla 42",
        "sku": "CLT-SNK-W-42-Z",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "ZGZ",
        "current_stock": 12,
    },
    {
        "id": 2,
        "name": "Auriculares inalambricos Pro",
        "sku": "TEC-EAR-001",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "LA",
        "current_stock": 3,
    },
]


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_query_inventory_lists_full_catalog():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/inventory/products"
        return httpx.Response(200, json=_CATALOG)

    result = query_inventory(QueryInventoryInput(sku=None), client=_client_for(handler))

    assert result.ok is True
    assert len(result.products) == 2


def test_query_inventory_filters_by_sku():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_CATALOG)

    result = query_inventory(QueryInventoryInput(sku="TEC-EAR-001"), client=_client_for(handler))

    assert result.ok is True
    assert len(result.products) == 1
    assert result.products[0].sku == "TEC-EAR-001"


def test_query_inventory_sku_not_found_is_honest():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_CATALOG)

    result = query_inventory(QueryInventoryInput(sku="DOES-NOT-EXIST"), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "not_found"


def test_query_inventory_timeout_is_named_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    result = query_inventory(QueryInventoryInput(sku=None), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "timeout"


def test_update_inventory_stock_always_rejects_explicitly():
    """No un generico "error", ni silencio: un codigo documentado
    (`read_only_tool`) que un agente puede distinguir de una falla real."""

    result = update_inventory_stock(UpdateInventoryStockInput(sku="TEC-EAR-001", quantity_delta=10))

    assert result.ok is False
    assert result.error == READ_ONLY_REJECTION_ERROR == "read_only_tool"
    assert result.products == []


def test_inventory_module_has_no_write_capability():
    """La tool de inventario es de solo lectura incluso a nivel de codigo:
    ni una sola llamada de escritura HTTP existe en el modulo."""

    import tools.inventory_tools as module

    source = Path(module.__file__).read_text()
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source
