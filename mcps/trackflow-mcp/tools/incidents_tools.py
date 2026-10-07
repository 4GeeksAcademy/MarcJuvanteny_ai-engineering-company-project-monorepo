"""Tool obligatoria: gestion de tickets del Incidents Manager (crear,
actualizar estado, consultar) -- checklist "Servidor MCP".

Lee y escribe el backend real de `services/incidents-api`
(`POST /api/incidents`, `GET /api/incidents`, `GET /api/incidents/{id}`,
`PATCH /api/incidents/{id}/status`) -- nunca datos simulados. Los mismos
nombres de campo, IDs y valores de dominio que expone esa API real (ver
`services/incidents-api/models.py`): categorias, branches, origenes y
estados son los mismos enums, copiados aca solo para que el schema de
entrada de la tool (descubrible via MCP sin contexto humano) los documente
explicitamente en vez de aceptar cualquier string.

Los cambios de estado pasan EXCLUSIVAMENTE por
`PATCH /api/incidents/{id}/status` (el endpoint de ciclo de vida real, que ya
valida transiciones validas: open -> in_progress/discarded,
in_progress -> resolved/discarded, resolved/discarded son terminales) --
nunca un PATCH generico sobre el recurso de incidencia completo.

Cada funcion de tool acepta un `client: httpx.Client` inyectable para tests
deterministas offline (`httpx.MockTransport`, mismo patron que
`services/knowledge-api/tools/*.py`), y un `timeout` explicito y numerico
(nunca implicito) para que una tool nunca deje al MCP Server colgado.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend_client import DEFAULT_TIMEOUT_SECONDS, INCIDENTS_API_URL, auth_headers

VALID_INCIDENT_CATEGORIES = ["lost_parcel", "carrier_issue", "inventory_discrepancy"]
VALID_INCIDENT_ORIGINS = ["customer", "branch", "internal"]
VALID_BRANCHES = ["la_warehouse", "la_office", "zaragoza_warehouse", "zaragoza_office", "central"]
VALID_INCIDENT_STATUSES = ["open", "in_progress", "resolved", "discarded"]


class IncidentRecordOutput(BaseModel):
    """Los mismos campos que expone `IncidentRecord` en
    `services/incidents-api/models.py` -- ni mas ni menos."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    description: str
    category: str
    origin: str
    branch: str
    status: str
    source_incident_id: str | None = None
    created_at: str
    updated_at: str


class IncidentToolOutput(BaseModel):
    """`ok=False` -> ver `error` (`"timeout"`, `"not_found"`,
    `"unauthorized"`, `"connection_error:..."`, `"validation_error:..."`,
    etc.) -- la tool nunca inventa un resultado cuando `ok=False`."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    incidents: list[IncidentRecordOutput] = []
    error: str | None = None


# --- consultar (GET /api/incidents, /api/incidents/{id}) --------------------


class QueryIncidentInput(BaseModel):
    """Entrada: `incident_id` puntual, o filtros de busqueda -- los mismos
    query params que expone `GET /api/incidents`."""

    model_config = ConfigDict(extra="forbid")

    incident_id: int | None = Field(default=None, description="ID puntual de un ticket. Si se da, ignora los filtros.")
    status: str | None = Field(default=None, description=f"Uno de: {VALID_INCIDENT_STATUSES}")
    origin: str | None = Field(default=None, description=f"Uno de: {VALID_INCIDENT_ORIGINS}")
    branch: str | None = Field(default=None, description=f"Uno de: {VALID_BRANCHES}")
    category: str | None = Field(default=None, description=f"Uno de: {VALID_INCIDENT_CATEGORIES}")


def query_incident(
    query: QueryIncidentInput,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> IncidentToolOutput:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout)

    try:
        if query.incident_id is not None:
            response = active_client.get(
                f"{INCIDENTS_API_URL}/api/incidents/{query.incident_id}", headers=auth_headers(), timeout=timeout
            )
        else:
            params = {
                key: value
                for key, value in {
                    "status": query.status,
                    "origin": query.origin,
                    "branch": query.branch,
                    "category": query.category,
                }.items()
                if value is not None
            }
            response = active_client.get(
                f"{INCIDENTS_API_URL}/api/incidents", headers=auth_headers(), params=params, timeout=timeout
            )
    except httpx.TimeoutException:
        return IncidentToolOutput(ok=False, error="timeout")
    except httpx.RequestError as exc:
        return IncidentToolOutput(ok=False, error=f"connection_error:{exc}")
    finally:
        if owns_client:
            active_client.close()

    if response.status_code == 404:
        return IncidentToolOutput(ok=False, error="not_found")
    if response.status_code == 401:
        return IncidentToolOutput(ok=False, error="unauthorized")
    if response.status_code != 200:
        return IncidentToolOutput(ok=False, error=f"unexpected_status:{response.status_code}")

    payload = response.json()
    records = payload if isinstance(payload, list) else [payload]
    return IncidentToolOutput(ok=True, incidents=[IncidentRecordOutput.model_validate(record) for record in records])


# --- crear (POST /api/incidents) ---------------------------------------------


class CreateIncidentTicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str = Field(description=f"Uno de: {VALID_INCIDENT_CATEGORIES}")
    origin: str = Field(description=f"Uno de: {VALID_INCIDENT_ORIGINS}")
    branch: str = Field(description=f"Uno de: {VALID_BRANCHES}")


def create_incident_ticket(
    payload: CreateIncidentTicketInput,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> IncidentToolOutput:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout)

    try:
        response = active_client.post(
            f"{INCIDENTS_API_URL}/api/incidents",
            headers=auth_headers(),
            json=payload.model_dump(),
            timeout=timeout,
        )
    except httpx.TimeoutException:
        return IncidentToolOutput(ok=False, error="timeout")
    except httpx.RequestError as exc:
        return IncidentToolOutput(ok=False, error=f"connection_error:{exc}")
    finally:
        if owns_client:
            active_client.close()

    if response.status_code == 401:
        return IncidentToolOutput(ok=False, error="unauthorized")
    if response.status_code == 422:
        return IncidentToolOutput(ok=False, error=f"validation_error:{response.text}")
    if response.status_code != 201:
        return IncidentToolOutput(ok=False, error=f"unexpected_status:{response.status_code}")

    return IncidentToolOutput(ok=True, incidents=[IncidentRecordOutput.model_validate(response.json())])


# --- actualizar estado (PATCH /api/incidents/{id}/status) -------------------


class UpdateIncidentStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: int = Field(gt=0)
    status: str = Field(description=f"Uno de: {VALID_INCIDENT_STATUSES}")


def update_incident_status(
    payload: UpdateIncidentStatusInput,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> IncidentToolOutput:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout)

    try:
        response = active_client.patch(
            f"{INCIDENTS_API_URL}/api/incidents/{payload.incident_id}/status",
            headers=auth_headers(),
            json={"status": payload.status},
            timeout=timeout,
        )
    except httpx.TimeoutException:
        return IncidentToolOutput(ok=False, error="timeout")
    except httpx.RequestError as exc:
        return IncidentToolOutput(ok=False, error=f"connection_error:{exc}")
    finally:
        if owns_client:
            active_client.close()

    if response.status_code == 404:
        return IncidentToolOutput(ok=False, error="not_found")
    if response.status_code == 401:
        return IncidentToolOutput(ok=False, error="unauthorized")
    if response.status_code == 400:
        return IncidentToolOutput(ok=False, error=f"invalid_transition:{response.text}")
    if response.status_code != 200:
        return IncidentToolOutput(ok=False, error=f"unexpected_status:{response.status_code}")

    return IncidentToolOutput(ok=True, incidents=[IncidentRecordOutput.model_validate(response.json())])
