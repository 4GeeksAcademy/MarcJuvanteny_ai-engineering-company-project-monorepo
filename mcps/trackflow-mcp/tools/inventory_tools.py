"""Tool extra: consulta de inventario -- checklist "Servidor MCP", "Exponer
al menos una tool de solo consulta sobre el inventario -- cualquier intento
de modificacion debe ser rechazado explicitamente por el servidor, no
simplemente omitido."

Lee `GET /inventory/products` real (`services/incidents-api/routers/inventory.py`)
-- no acepta filtros del lado del servidor, asi que el filtrado por SKU
mencionado en la consulta se hace sobre la respuesta real, no sobre datos
inventados. Ese endpoint no requiere auth en el backend (ver
`get_current_inventory_user` vs. las rutas GET, que no lo usan) -- se manda
`INCIDENTS_API_TOKEN` de todas formas por consistencia, es inofensivo.

Cumplimiento de "rechazado explicitamente, no simplemente omitido": no
alcanza con no registrar una tool de escritura -- un cliente que intente
invocar una para modificar stock debe recibir un rechazo claro y
documentado, no un error generico ni silencio. Por eso se expone
`update_inventory_stock` como una tool real y descubrible (aparece en
`tools/list`, con su proposito documentado) cuyo UNICO comportamiento es
devolver ese rechazo -- nunca llama a ningun endpoint de escritura del
backend (el unico verbo HTTP que usa este modulo es GET, ver
`tests/test_inventory_tools.py::test_inventory_module_has_no_write_capability`).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend_client import DEFAULT_TIMEOUT_SECONDS, INCIDENTS_API_URL, auth_headers

READ_ONLY_REJECTION_ERROR = "read_only_tool"
READ_ONLY_REJECTION_MESSAGE = (
    "read_only_tool: la tool de inventario de TrackFlow es de solo lectura. "
    "No esta permitido crear, actualizar ni eliminar stock a traves del MCP Server."
)


class ProductOutput(BaseModel):
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
    products: list[ProductOutput] = []
    error: str | None = None


class QueryInventoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str | None = Field(default=None, description="SKU exacto a filtrar. Si se omite, devuelve el catalogo completo.")


def query_inventory(
    query: QueryInventoryInput,
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

    products = [ProductOutput.model_validate(record) for record in response.json()]
    if query.sku is not None:
        products = [product for product in products if product.sku == query.sku]
        if not products:
            return InventoryToolOutput(ok=False, error="not_found")

    return InventoryToolOutput(ok=True, products=products)


class UpdateInventoryStockInput(BaseModel):
    """Existe solo para que la tool sea descubrible con un contrato de
    entrada claro (ver el modulo). Nunca se usa para escribir nada."""

    model_config = ConfigDict(extra="forbid")

    sku: str
    quantity_delta: int


def update_inventory_stock(payload: UpdateInventoryStockInput) -> InventoryToolOutput:
    """Rechaza SIEMPRE, sin llamar al backend. Ver docstring del modulo."""

    _ = payload
    return InventoryToolOutput(ok=False, error=READ_ONLY_REJECTION_ERROR)
