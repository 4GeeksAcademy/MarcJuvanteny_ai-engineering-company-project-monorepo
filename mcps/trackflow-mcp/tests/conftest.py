from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SERVICE_DIR = TESTS_DIR.parent
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(TESTS_DIR))

from mcpauth import MCPAuth  # noqa: E402
from mcpauth.utils import create_verify_jwt  # noqa: E402

from auth import build_auth_server_config  # noqa: E402
from dev_idp import TEST_AUDIENCE, TEST_ISSUER, DevIdP  # noqa: E402


@pytest.fixture()
def dev_idp() -> DevIdP:
    return DevIdP()


@pytest.fixture()
def test_mcp_auth(dev_idp: DevIdP) -> MCPAuth:
    """`MCPAuth` real (misma clase, misma logica de verificacion/issuer/
    audience/scopes que produccion) construido contra el emisor de prueba
    local -- ver `dev_idp.py`."""

    server_config = build_auth_server_config(TEST_ISSUER)
    return MCPAuth(server=server_config)


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def test_verify_fn(dev_idp: DevIdP):
    """Funcion de verificacion real (`mcpauth.utils.create_verify_jwt`) que
    valida la firma RS256 contra la clave publica del emisor de prueba, sin
    red (la `PyJWK` se construye en memoria, no via `jwks_uri` HTTP)."""

    return create_verify_jwt(dev_idp.public_jwk())
