"""Emisor de prueba local para tests (NUNCA produccion -- ver `auth.py`,
seccion "Produccion vs. desarrollo/tests"): genera un par de claves RSA real
en memoria y firma JWTs RS256 reales con `PyJWT`. No hay red, no hay
proveedor externo, pero la verificacion de firma que corre en los tests es
la misma que correria contra un IdP real (mismo algoritmo, mismo codigo de
`mcpauth`) -- el unico "stand-in" es que la clave la generamos nosotros en
vez de un proveedor OAuth 2.1/OIDC de terceros, exactamente como el
embedding lexico local reemplaza al de 4Geeks en `data/eval/evaluate_retrieval.py`.
"""

from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

TEST_ISSUER = "https://dev-idp.trackflow.test"
TEST_AUDIENCE = "trackflow-mcp"
TEST_KEY_ID = "dev-idp-test-key-1"


class DevIdP:
    def __init__(self):
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def public_jwk(self) -> PyJWK:
        jwk_dict = RSAAlgorithm.to_jwk(self._private_key.public_key(), as_dict=True)
        jwk_dict["kid"] = TEST_KEY_ID
        jwk_dict["use"] = "sig"
        return PyJWK.from_dict(jwk_dict, algorithm="RS256")

    def issue_token(
        self,
        *,
        subject: str = "test-client",
        client_id: str = "test-client-app",
        scopes: list[str] | None = None,
        audience: str | None = TEST_AUDIENCE,
        issuer: str = TEST_ISSUER,
        expires_in_seconds: int = 300,
    ) -> str:
        now = int(time.time())
        payload = {
            "iss": issuer,
            "sub": subject,
            "client_id": client_id,
            "scope": " ".join(scopes or []),
            "iat": now,
            "exp": now + expires_in_seconds,
        }
        if audience is not None:
            payload["aud"] = audience

        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": TEST_KEY_ID})
