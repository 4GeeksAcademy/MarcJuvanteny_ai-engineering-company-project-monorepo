"""Emisor OAuth 2.1 / OIDC de DESARROLLO -- NUNCA producción (ver `auth.py`,
sección "Producción vs. desarrollo/tests"). Promovido de `tests/dev_idp.py`
(que genera una clave y firma tokens en memoria, dentro del proceso de
pytest) a un proceso HTTP real y persistente, necesario para dos casos que
un test no cubre:

1. **Validación manual en MCP Playground**: un cliente externo (Playground,
   corriendo en otra máquina) necesita un access token de verdad para
   probar el servidor MCP público -- no alcanza con un token generado
   dentro de un proceso de test que termina al instante.
2. **El agente de `services/knowledge-api` como cliente MCP real**
   (`agent_graph.py`, via `langchain-mcp-adapters`): necesita pedir un
   token contra ALGÚN emisor en cada corrida, no solo dentro de un test.

Sirve las mismas rutas `.well-known/*` que un proveedor OIDC real --
`server.py::build_mcp_auth_from_env()` (`fetch_server_config()`) las
consume sin ningún cambio, tal como consumiría las de un proveedor real. La
única pieza que NO es parte de ningún RFC es `POST /mint-token`: un atajo de
desarrollo explícito (reemplaza el flujo interactivo real de autorización +
PKCE que un usuario humano completaría en un navegador) para emitir JWTs
RS256 reales sin necesidad de implementar ese flujo completo solo para
desarrollo local.

La clave RSA se genera una vez al arrancar el proceso y vive solo en
memoria -- reiniciar este proceso invalida cualquier token emitido antes
(aceptable: es un emisor de desarrollo, no debe sobrevivir un reinicio).
"""

from __future__ import annotations

import os
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

PORT = int(os.environ.get("DEV_IDP_PORT", "9999"))
ISSUER = os.environ.get("DEV_IDP_ISSUER", f"http://localhost:{PORT}")
KEY_ID = "dev-idp-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_jwk() -> dict:
    jwk = RSAAlgorithm.to_jwk(_private_key.public_key(), as_dict=True)
    jwk["kid"] = KEY_ID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return jwk


async def openid_configuration(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
        }
    )


async def jwks(request: Request) -> JSONResponse:
    return JSONResponse({"keys": [_public_jwk()]})


async def mint_token(request: Request) -> JSONResponse:
    """Atajo de desarrollo, no un endpoint OAuth real -- ver docstring del
    módulo. Body: `{"scopes": [...], "audience": "...", "subject": "...",
    "client_id": "...", "expires_in_seconds": 3600}` (todos opcionales
    salvo `scopes`)."""

    body = await request.json()
    scopes: list[str] = body.get("scopes", [])
    audience = body.get("audience")
    subject = body.get("subject", "dev-client")
    client_id = body.get("client_id", "dev-client-app")
    expires_in_seconds = int(body.get("expires_in_seconds", 3600))

    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "sub": subject,
        "client_id": client_id,
        "scope": " ".join(scopes),
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    if audience:
        payload["aud"] = audience

    private_pem = _private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": KEY_ID})
    return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": expires_in_seconds})


app = Starlette(
    routes=[
        Route("/.well-known/openid-configuration", openid_configuration),
        Route("/.well-known/jwks.json", jwks),
        Route("/mint-token", mint_token, methods=["POST"]),
    ]
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
