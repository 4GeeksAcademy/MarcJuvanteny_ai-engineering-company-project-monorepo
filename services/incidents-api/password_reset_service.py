from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from tinydb import TinyDB
from tinydb.table import Document

from auth_service import create_password_reset_token, decode_password_reset_token
from email_service import send_password_reset_email
from models import UserCredentialsUpdate
from user_service import get_user_by_email, update_user as update_user_service


def get_password_reset_base_url() -> str:
    return os.environ.get("BACKOFFICE_APP_URL", "http://localhost:3000").rstrip("/")


def _find_reset_token_document(tokens_table, jti: str) -> Document | None:
    for document in tokens_table.all():
        if document.get("jti") == jti:
            return document
    return None


def request_password_reset(db_path: Path, email: str) -> None:
    try:
        user = get_user_by_email(db_path, email)
    except HTTPException as exc:
        if exc.status_code == 404:
            return
        raise

    token, jti, expires_at = create_password_reset_token(user.id)

    with TinyDB(db_path) as db:
        tokens_table = db.table("password_reset_tokens")
        tokens_table.insert(
            {
                "jti": jti,
                "user_id": user.id,
                "expires_at": expires_at.isoformat(),
                "used": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    reset_link = f"{get_password_reset_base_url()}/reset-password?token={token}"
    send_password_reset_email(user.email, reset_link)


def confirm_password_reset(db_path: Path, token: str, new_password: str) -> None:
    payload = decode_password_reset_token(token)
    jti = payload.get("jti")
    subject = payload.get("sub")

    if not jti or subject is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")

    with TinyDB(db_path) as db:
        tokens_table = db.table("password_reset_tokens")
        record = _find_reset_token_document(tokens_table, jti)

        if record is None or record.get("used"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")

        tokens_table.update({"used": True}, doc_ids=[record.doc_id])

    update_user_service(db_path, int(subject), UserCredentialsUpdate(password=new_password))
