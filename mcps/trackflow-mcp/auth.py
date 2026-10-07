"""OAuth 2.1 / OIDC para el MCP Server, via MCP Auth (`mcpauth`, paquete
Python real -- ver https://mcp-auth.dev), NUNCA la capa OAuth/auth integrada
de FastMCP (`fastmcp.server.auth.AuthProvider`): el checklist la prohibe
explicitamente para este proyecto, y FastMCP no expone su propio flujo de
verificacion via bearer-middleware componible como MCP Auth, lo que haria
mas dificil auditar/documentar los codigos de error.

## Que valida MCP Auth aca

`MCPAuth.bearer_auth_middleware("jwt", ...)` (modulo real `mcpauth`, v0.1.1):
- Extrae el bearer token del header `Authorization`.
- Verifica la firma del JWT contra el JWKS del `issuer` configurado (RS256 /
  PS256 / ES256 -- algoritmos asimetricos, nunca HS256 con secreto compartido
  -- `mcpauth/utils/_create_verify_jwt.py`).
- Verifica `iss` (issuer) y, si `MCPAUTH_AUDIENCE` esta seteado, `aud`.
- Guarda un `AuthInfo` (subject, client_id, scopes, claims) accesible desde
  cualquier tool via `mcp_auth.auth_info` (contextvar) -- ver `tools/*.py`
  para el chequeo de scopes por-tool (ver docstring de `server.py` sobre por
  que el scope-check es manual y no via `required_scopes` global).

## Protected Resource Metadata (RFC 9728)

`mcpauth` 0.1.1 solo expone `metadata_endpoint()`/`metadata_route()` para el
endpoint de OAuth 2.0 Authorization Server Metadata (RFC 8414,
`/.well-known/oauth-authorization-server`) -- NO implementa el endpoint de
Protected Resource Metadata (RFC 9728, `/.well-known/oauth-protected-resource`)
que el checklist pide explicitamente ("monta Protected Resource Metadata").
Como RFC 9728 define un documento estatico simple (identificador del recurso
+ lista de authorization servers), se implementa aca a mano
(`protected_resource_metadata_route`) en vez de simularlo con datos falsos --
es un documento de descubrimiento publico, no un dato de negocio.

## Produccion vs. desarrollo/tests

- Produccion: `MCPAUTH_ISSUER` (+ opcional `MCPAUTH_SERVER_TYPE=oidc|oauth`)
  apunta a un proveedor OAuth 2.1 / OIDC real (Auth0, Logto, Keycloak, Okta,
  etc.) -- `fetch_server_config()` descubre el resto de la metadata via su
  endpoint `.well-known/*` real.
- Este repo no tiene credenciales de un proveedor OIDC real. Para
  desarrollo/tests se usa un emisor de prueba local
  (`tests/dev_idp.py` -- par de claves RSA generado en el momento, JWTs
  RS256 reales, sin red) -- documentado y nunca usado para produccion (ver
  `Pasos/mcp-server-tools.md`, seccion "Decisiones de implementacion").
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mcpauth import MCPAuth
from mcpauth.config import AuthorizationServerMetadata, AuthServerConfig, AuthServerType
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

load_dotenv(Path(__file__).resolve().parent / ".env")

MCPAUTH_ISSUER = os.environ.get("MCPAUTH_ISSUER", "")
MCPAUTH_AUDIENCE = os.environ.get("MCPAUTH_AUDIENCE") or None
MCPAUTH_SERVER_TYPE = os.environ.get("MCPAUTH_SERVER_TYPE", "oidc")
MCP_SERVER_RESOURCE_URL = os.environ.get("MCP_SERVER_RESOURCE_URL", "http://localhost:8010/mcp")

PROTECTED_RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"


def build_auth_server_config(
    issuer: str,
    *,
    authorization_endpoint: str | None = None,
    token_endpoint: str | None = None,
    jwks_uri: str | None = None,
) -> AuthServerConfig:
    """Config explicita del authorization server (sin red), usada por los
    tests y por despliegues que prefieren no depender del discovery
    `fetch_server_config()` (ej. un JWKS local para el emisor de prueba)."""

    return AuthServerConfig(
        type=AuthServerType.OIDC if MCPAUTH_SERVER_TYPE == "oidc" else AuthServerType.OAUTH,
        metadata=AuthorizationServerMetadata(
            issuer=issuer,
            authorization_endpoint=authorization_endpoint or f"{issuer}/authorize",
            token_endpoint=token_endpoint or f"{issuer}/token",
            jwks_uri=jwks_uri or f"{issuer}/.well-known/jwks.json",
            response_types_supported=["code"],
            code_challenge_methods_supported=["S256"],
        ),
    )


def build_mcp_auth_from_env() -> MCPAuth:
    """Descubre la metadata del authorization server real configurado en
    `MCPAUTH_ISSUER` (via su endpoint `.well-known/*`) y arma el `MCPAuth`
    que protege este servidor. Usado por `server.py` en produccion."""

    if not MCPAUTH_ISSUER:
        raise RuntimeError(
            "MCPAUTH_ISSUER no esta configurado. El MCP Server no puede arrancar sin un "
            "authorization server OAuth 2.1 / OIDC real -- ver .env.example."
        )

    from mcpauth.utils import fetch_server_config

    server_type = AuthServerType.OIDC if MCPAUTH_SERVER_TYPE == "oidc" else AuthServerType.OAUTH
    server_config = fetch_server_config(MCPAUTH_ISSUER, type=server_type)
    return MCPAuth(server=server_config)


def protected_resource_metadata_endpoint(resource_url: str, issuer: str):
    """Endpoint RFC 9728 escrito a mano (ver docstring del modulo): un
    documento de descubrimiento publico y estatico, no un dato de negocio
    simulado."""

    async def endpoint(request: Request) -> Response:
        if request.method == "OPTIONS":
            response = Response(status_code=204)
        else:
            response = JSONResponse(
                {
                    "resource": resource_url,
                    "authorization_servers": [issuer],
                },
                status_code=200,
            )
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    return endpoint


def protected_resource_metadata_route(resource_url: str, issuer: str) -> Route:
    return Route(
        PROTECTED_RESOURCE_METADATA_PATH,
        protected_resource_metadata_endpoint(resource_url, issuer),
        methods=["GET", "OPTIONS"],
    )
