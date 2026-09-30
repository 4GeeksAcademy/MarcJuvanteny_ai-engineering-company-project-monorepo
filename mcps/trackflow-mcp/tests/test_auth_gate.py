"""Tests del middleware de bearer auth de MCP Auth en aislamiento (sin pasar
por el protocolo MCP completo) -- checklist "Ningun cliente sin access token
valido puede listar ni invocar tools" / "Definir y documentar los codigos de
error esperados ante fallos de autenticacion, autorizacion o validacion".

Usa una app Starlette minima envuelta con el MISMO middleware que produce
`mcp_auth.bearer_auth_middleware(...)` (la clase real de `mcpauth`, no un
doble), contra el emisor de prueba de `dev_idp.py` -- prueba exactamente la
logica de verificacion de firma/issuer/audience/scopes que protege
`server.py`, sin la complejidad adicional del transporte MCP en si (eso lo
cubre `test_server_integration.py`).
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dev_idp import TEST_AUDIENCE, TEST_ISSUER, DevIdP


async def _ok_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _build_protected_app(mcp_auth, verify_fn, *, required_scopes):
    bearer_auth = mcp_auth.bearer_auth_middleware(verify_fn, audience=TEST_AUDIENCE, required_scopes=required_scopes)
    return Starlette(
        routes=[Route("/protected", _ok_endpoint)],
        middleware=[ASGIMiddleware(bearer_auth)],
    )


def test_request_without_token_is_rejected_with_documented_code(test_mcp_auth, test_verify_fn):
    app = _build_protected_app(test_mcp_auth, test_verify_fn, required_scopes=["mcp:access"])
    client = TestClient(app)

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json()["error"] == "missing_auth_header"


def test_request_with_garbage_token_is_rejected(test_mcp_auth, test_verify_fn):
    app = _build_protected_app(test_mcp_auth, test_verify_fn, required_scopes=["mcp:access"])
    client = TestClient(app)

    response = client.get("/protected", headers={"Authorization": "Bearer not-a-real-jwt"})

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


def test_request_with_valid_token_but_wrong_issuer_is_rejected(dev_idp: DevIdP, test_mcp_auth, test_verify_fn):
    token = dev_idp.issue_token(scopes=["mcp:access"], issuer="https://some-other-idp.example")

    app = _build_protected_app(test_mcp_auth, test_verify_fn, required_scopes=["mcp:access"])
    client = TestClient(app)

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_issuer"


def test_request_missing_required_scope_gets_403_not_401(dev_idp: DevIdP, test_mcp_auth, test_verify_fn):
    """Distincion documentada: sin token / token invalido -> 401;
    token valido pero sin el scope -> 403 (`mcpauth` real, ver
    `middleware/create_bearer_auth.py::_handle_error`)."""

    token = dev_idp.issue_token(scopes=["some:other:scope"])

    app = _build_protected_app(test_mcp_auth, test_verify_fn, required_scopes=["mcp:access"])
    client = TestClient(app)

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["error"] == "missing_required_scopes"


def test_request_with_valid_token_and_scope_passes_through(dev_idp: DevIdP, test_mcp_auth, test_verify_fn):
    token = dev_idp.issue_token(scopes=["mcp:access"])

    app = _build_protected_app(test_mcp_auth, test_verify_fn, required_scopes=["mcp:access"])
    client = TestClient(app)

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
