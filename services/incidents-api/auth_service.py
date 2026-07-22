from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from user_service import get_user_by_email, get_user_by_id

load_dotenv(Path(__file__).resolve().parent / ".env")

ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET_KEY is not configured.",
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


def verify_password(plain_password: str, stored_hash: str) -> bool:
    if not stored_hash.startswith("sha256$"):
        return False

    parts = stored_hash.split("$", 2)
    if len(parts) != 3:
        return False

    _, salt, expected_digest = parts
    computed_digest = hashlib.sha256(f"{salt}:{plain_password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed_digest, expected_digest)


def authenticate_user(db_path: Path, email: str, password: str):
    try:
        user = get_user_by_email(db_path, email)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise

    if not verify_password(password, user.hashed_password):
        return None

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
