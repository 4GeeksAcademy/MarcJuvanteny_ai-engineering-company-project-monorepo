from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from models import UserCredentialsUpdate
from password_hashing import needs_rehash
from password_hashing import verify_password as _verify_password_hash
from user_service import get_user_by_email, get_user_by_id, update_user

load_dotenv(Path(__file__).resolve().parent / ".env")

ALGORITHM = "HS256"


MIN_JWT_SECRET_LENGTH = 32


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET_KEY is not configured.",
        )
    # Hito 12 (credenciales): HS256 con un secreto corto se fuerza por
    # diccionario/fuerza bruta offline a partir de UN token capturado. RFC 7518
    # §3.2: clave >= tamaño del hash (256 bits). Falla cerrado: sin secreto
    # válido no se emite ni se acepta ningún token.
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise HTTPException(
            status_code=500,
            detail=f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters.",
        )
    return secret


def get_access_token_expire_minutes() -> int:
    raw_value = os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    try:
        minutes = int(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="ACCESS_TOKEN_EXPIRE_MINUTES must be an integer.") from exc

    if minutes <= 0:
        raise HTTPException(status_code=500, detail="ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero.")

    return minutes


def get_reset_token_expire_minutes() -> int:
    raw_value = os.environ.get("RESET_TOKEN_EXPIRE_MINUTES", "30")
    try:
        minutes = int(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="RESET_TOKEN_EXPIRE_MINUTES must be an integer.") from exc

    if not (15 <= minutes <= 60):
        raise HTTPException(
            status_code=500,
            detail="RESET_TOKEN_EXPIRE_MINUTES must be between 15 and 60.",
        )

    return minutes


def verify_password(plain_password: str, stored_hash: str) -> bool:
    # scrypt + compatibilidad con el sha256 heredado -- ver password_hashing.py.
    return _verify_password_hash(plain_password, stored_hash)


def authenticate_user(db_path: Path, email: str, password: str):
    try:
        user = get_user_by_email(db_path, email)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise

    if not verify_password(password, user.hashed_password):
        return None

    if needs_rehash(user.hashed_password):
        # Migración transparente sha256 -> scrypt en el primer login correcto.
        update_user(db_path, user.id, UserCredentialsUpdate(password=password))

    return user


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    expires_minutes = get_access_token_expire_minutes()
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)
    return token, expires_minutes


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload


def create_password_reset_token(user_id: int) -> tuple[str, str, datetime]:
    expires_minutes = get_reset_token_expire_minutes()
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    jti = secrets.token_hex(16)

    payload = {
        "sub": str(user_id),
        "purpose": "password_reset",
        "jti": jti,
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)
    return token, jti, expire_at


def decode_password_reset_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token.",
        ) from exc

    if payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")

    return payload


def get_user_from_token(db_path: Path, token: str):
    payload = decode_access_token(token)
    subject = payload.get("sub")

    if subject is None:
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

    try:
        user = get_user_by_id(db_path, user_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found for token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
