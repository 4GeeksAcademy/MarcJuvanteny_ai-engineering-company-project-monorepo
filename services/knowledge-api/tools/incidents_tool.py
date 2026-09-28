"""Tool obligatoria: consulta de tickets de soporte (`CONTEXT7.md`, sección
"Tool obligatoria").

Lee de `services/incidents-api` real por HTTP (`GET /api/incidents` /
`GET /api/incidents/{id}`) — nunca datos simulados ni hardcodeados. Elegido
HTTP (no en-proceso) porque `incidents-api` y `knowledge-api` son procesos y
paquetes separados en este monorepo (cada uno con su propio venv/deploy),
así que "en-proceso" no aplica a esta arquitectura.

**Solo lectura**: únicamente `GET`. Esta tool no tiene ninguna función que
haga `POST`/`PATCH`/`DELETE` — no puede crear, actualizar ni eliminar
tickets aunque quisiera, esas operaciones ni están importadas acá.
"""

from __future__ import annotations

import re

import httpx
from pydantic import BaseModel, ConfigDict

from tools.backend_client import DEFAULT_TIMEOUT_SECONDS, INCIDENTS_API_URL, auth_headers

_STATUS_KEYWORDS = {
    "abiertos": "open",
    "abierto": "open",
    "en progreso": "in_progress",
    "resueltos": "resolved",
    "resuelto": "resolved",
    "descartados": "discarded",
    "descartado": "discarded",
}
_TICKET_ID_RE = re.compile(r"\b(\d+)\b")


class IncidentQueryInput(BaseModel):
    """Contrato de entrada: `incident_id` o filtros de búsqueda -- los mismos
    query params que expone `GET /api/incidents` (Sección "Tool obligatoria")."""

    model_config = ConfigDict(extra="forbid")

    incident_id: int | None = None
    status: str | None = None
    origin: str | None = None
    branch: str | None = None
    category: str | None = None


class IncidentSummary(BaseModel):
    """Mismos campos que expone `IncidentRecord` en `services/incidents-api/models.py`."""

    model_config = ConfigDict(extra="ignore")  # la API puede traer mas campos que la tool no usa

    id: int
    title: str
    status: str
    category: str
    origin: str
    branch: str
    created_at: str
    updated_at: str


class IncidentToolOutput(BaseModel):
    """Contrato de salida. `ok=False` -> ver `error` (`"timeout"`,
    `"not_found"`, `"unauthorized"`, `"connection_error:..."`, etc.) -- el
    grafo decide la ruta de fallback a partir de este campo, nunca inventa
    un estado."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    incidents: list[IncidentSummary] = []
    error: str | None = None


def extract_incident_query(question: str) -> IncidentQueryInput:
    """Heurística determinista y documentada (no un LLM real, sin
    credenciales en este repo) para extraer `incident_id`/`status` de una
    pregunta en lenguaje natural: un número suelto se interpreta como
    `incident_id`; si no hay número, palabras clave de estado
    (`"abiertos"`, `"resueltos"`, etc.) arman un filtro `status`; si
    tampoco hay eso, no se aplica filtro (lista todos)."""
    match = _TICKET_ID_RE.search(question)
    if match:
        return IncidentQueryInput(incident_id=int(match.group(1)))

    lowered = question.lower()
    for keyword, status in _STATUS_KEYWORDS.items():
        if keyword in lowered:
            return IncidentQueryInput(status=status)

    return IncidentQueryInput()


def query_incidents(
    query: IncidentQueryInput,
    *,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> IncidentToolOutput:
    """Llama a `GET /api/incidents/{id}` o `GET /api/incidents` (con
    filtros). `client` inyectable (`httpx.Client(transport=httpx.MockTransport(...))`
    en tests, sin red real) -- ver `tests/pipelines/test_agent_tools.py`.
    """
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
    return IncidentToolOutput(ok=True, incidents=[IncidentSummary.model_validate(record) for record in records])
