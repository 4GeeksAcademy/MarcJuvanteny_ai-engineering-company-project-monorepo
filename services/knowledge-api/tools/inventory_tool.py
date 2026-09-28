"""Tool opcional: consulta de inventario (`CONTEXT7.md`, sección "Tool
extra (opcional)"). TrackFlow sí tiene un gestor de inventario construido
(`services/incidents-api/routers/inventory.py`), así que se implementa.

Mismas reglas que la tool de incidentes: solo lectura (`GET`), timeout
explícito, fallback honesto, sin datos simulados — lee de
`GET /inventory/products` real.

`GET /inventory/products` no acepta filtros por SKU en el backend (devuelve
todo el catálogo, ~8-15 SKUs por diseño) — el filtrado por SKU mencionado en
la pregunta se hace del lado de la tool, sobre la respuesta real de la API,
no sobre datos inventados.
"""

from __future__ import annotations

import re

import httpx
from pydantic import BaseModel, ConfigDict

from tools.backend_client import DEFAULT_TIMEOUT_SECONDS, INCIDENTS_API_URL, auth_headers

_SKU_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+){2,}\b")


class InventoryQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str | None = None


class ProductSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    sku: str
    client_name: str
    category: str
    warehouse: str
    current_stock: int


class InventoryToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    products: list[ProductSummary] = []
    error: str | None = None


def extract_inventory_query(question: str) -> InventoryQueryInput:
    """Heurística determinista: un token con forma de SKU
    (`CLT-SNK-W-42-Z`) en la pregunta se usa para filtrar la respuesta;
    si no hay ninguno, no se filtra (se devuelve el catálogo completo)."""
    match = _SKU_RE.search(question.upper())
    return InventoryQueryInput(sku=match.group(0) if match else None)


def query_inventory(
    query: InventoryQueryInput,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> InventoryToolOutput:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout)

    try:
        response = active_client.get(f"{INCIDENTS_API_URL}/inventory/products", headers=auth_headers(), timeout=timeout)
    except httpx.TimeoutException:
        return InventoryToolOutput(ok=False, error="timeout")
    except httpx.RequestError as exc:
        return InventoryToolOutput(ok=False, error=f"connection_error:{exc}")
    finally:
        if owns_client:
            active_client.close()

    if response.status_code != 200:
        return InventoryToolOutput(ok=False, error=f"unexpected_status:{response.status_code}")

    products = [ProductSummary.model_validate(record) for record in response.json()]
    if query.sku is not None:
        products = [product for product in products if product.sku == query.sku]
        if not products:
            return InventoryToolOutput(ok=False, error="not_found")

    return InventoryToolOutput(ok=True, products=products)
