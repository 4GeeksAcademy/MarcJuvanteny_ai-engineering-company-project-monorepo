"""Tests de `tools/incidents_tools.py` (tool obligatoria) via
`httpx.MockTransport` -- mismo patron que
`tests/pipelines/test_agent_tools.py` en el repo raiz. Verifica que la tool
lee/escribe los mismos paths y payloads que expone
`services/incidents-api/main.py` de verdad."""

from __future__ import annotations

import httpx

from tools.incidents_tools import (
    CreateIncidentTicketInput,
    QueryIncidentInput,
    UpdateIncidentStatusInput,
    create_incident_ticket,
    query_incident,
    update_incident_status,
)


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


_RECORD = {
    "id": 42,
    "title": "Paquete perdido",
    "description": "El paquete nunca llego",
    "category": "lost_parcel",
    "origin": "customer",
    "branch": "la_warehouse",
    "status": "open",
    "source_incident_id": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


def test_query_incident_by_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/incidents/42"
        return httpx.Response(200, json=_RECORD)

    result = query_incident(QueryIncidentInput(incident_id=42), client=_client_for(handler))

    assert result.ok is True
    assert result.incidents[0].status == "open"


def test_query_incident_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    result = query_incident(QueryIncidentInput(incident_id=999), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "not_found"


def test_query_incident_timeout_is_named_not_a_hang():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    result = query_incident(QueryIncidentInput(incident_id=1), client=_client_for(handler))

    assert result.ok is False
    assert result.error == "timeout"


def test_create_incident_ticket_posts_to_real_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/incidents"
        import json

        body = json.loads(request.content)
        assert body == {
            "title": "Paquete perdido",
            "description": "El paquete nunca llego",
            "category": "lost_parcel",
            "origin": "customer",
            "branch": "la_warehouse",
        }
        return httpx.Response(201, json=_RECORD)

    result = create_incident_ticket(
        CreateIncidentTicketInput(
            title="Paquete perdido",
            description="El paquete nunca llego",
            category="lost_parcel",
            origin="customer",
            branch="la_warehouse",
        ),
        client=_client_for(handler),
    )

    assert result.ok is True
    assert result.incidents[0].id == 42


def test_create_incident_ticket_validation_error_is_surfaced_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "category must be one of: [...]"})

    result = create_incident_ticket(
        CreateIncidentTicketInput(
            title="x", description="y", category="not_a_real_category", origin="customer", branch="la_warehouse"
        ),
        client=_client_for(handler),
    )

    assert result.ok is False
    assert result.error.startswith("validation_error")


def test_update_incident_status_uses_the_lifecycle_endpoint_only():
    """El checklist exige que los cambios de estado pasen por
    `PATCH /api/incidents/{id}/status`, nunca un PATCH generico sobre el
    recurso completo."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/api/incidents/42/status"
        import json

        assert json.loads(request.content) == {"status": "in_progress"}
        updated = dict(_RECORD, status="in_progress")
        return httpx.Response(200, json=updated)

    result = update_incident_status(
        UpdateIncidentStatusInput(incident_id=42, status="in_progress"),
        client=_client_for(handler),
    )

    assert result.ok is True
    assert result.incidents[0].status == "in_progress"


def test_update_incident_status_invalid_transition_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Cannot transition incident from 'resolved' to 'open'."})

    result = update_incident_status(
        UpdateIncidentStatusInput(incident_id=42, status="open"),
        client=_client_for(handler),
    )

    assert result.ok is False
    assert result.error.startswith("invalid_transition")


def test_update_incident_status_connection_error_is_named_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = update_incident_status(
        UpdateIncidentStatusInput(incident_id=1, status="in_progress"),
        client=_client_for(handler),
    )

    assert result.ok is False
    assert result.error.startswith("connection_error")
