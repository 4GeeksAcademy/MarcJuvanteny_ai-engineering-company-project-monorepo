"""Autenticacion (Fase 5 del diseno: "mismas convenciones de autenticacion que
el resto de tu API").

Mismo esquema Bearer/JWT y mismo `JWT_SECRET_KEY` que
`services/incidents-api` (`auth_service.py`), pero el token se decodifica
localmente en vez de resolverse contra la tabla de usuarios (`suppliers.json`
en incidents-api): `services/reporting/` no es dueno de ese store, solo
confia en la firma del JWT que incidents-api ya emitio en el login.
"""

from __future__ import annotations

import os
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel

SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)

# Roles autorizados a disparar una corrida manual (POST /exec-weekly/run):
# mismo criterio que "un director que quiere refrescar el consolidado antes
# del comite" (diseno, Fase 5.1) — no cualquier usuario autenticado.
MANUAL_TRIGGER_ROLES = {"admin", "manager"}


class Principal(BaseModel):
    user_id: int
    role: str


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY is not configured.")
    return secret


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(credentials.credentials, _get_jwt_secret(), algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = payload.get("sub")
    role = payload.get("role")
    if subject is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return Principal(user_id=user_id, role=role)


def require_manual_trigger_role(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role not in MANUAL_TRIGGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {sorted(MANUAL_TRIGGER_ROLES)} roles can trigger a manual run.",
        )
    return principal
