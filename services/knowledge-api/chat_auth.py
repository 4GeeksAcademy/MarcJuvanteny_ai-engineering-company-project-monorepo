"""Verificación del JWT del backoffice para el chat (`CONTEXT/CONTEXT10.md`,
Parte 2 §3: "Autentica el WebSocket con el mismo JWT que la API del
backoffice (y el SSE de la Parte 1)").

El token lo emite `services/incidents-api` (`auth_service.create_access_token`:
HS256, `JWT_SECRET_KEY`, `sub` = id del usuario). Este servicio solo lo
verifica -- firma + expiración con el MISMO secreto -- y nunca emite tokens
propios. `JWT_SECRET_KEY` debe ser idéntica en los dos servicios (ver
`.env.example`).
"""

from __future__ import annotations

import os
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Header, HTTPException, status
from jwt import InvalidTokenError

load_dotenv(Path(__file__).resolve().parent / ".env")

ALGORITHM = "HS256"


def user_id_from_token(token: str | None) -> str | None:
    """`user_id` (el `sub` del JWT) o `None` si falta, está mal firmado,
    expiró o el servicio no tiene secreto configurado -- quien llama decide
    cómo rechazar (401 por HTTP, close 4401 por WebSocket)."""

    secret = os.environ.get("JWT_SECRET_KEY")
    if not token or not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None
    subject = payload.get("sub")
    return str(subject) if subject is not None else None


def require_bearer_user(authorization: str | None = Header(default=None)) -> str:
    """Dependencia FastAPI para las rutas HTTP de este servicio (`/chat/*`,
    `/agent/*`, `/knowledge/*` -- auditoría OWASP A01: antes `/agent/query`
    y `/knowledge/query` eran anónimos, y por ellos cualquiera llegaba a las
    tools internas del agente y gastaba LLM). Devuelve el `user_id`."""

    scheme, _, token = (authorization or "").partition(" ")
    user_id = user_id_from_token(token) if scheme.lower() == "bearer" else None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"}
        )
    return user_id
