from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi import HTTPException
from tinydb import TinyDB
from tinydb.table import Document

from models import (
    ProfileUpdate,
    ProfileRecord,
    ProfileResponse,
    UserCreate,
    UserCredentialsUpdate,
    UserRecord,
    UserRegister,
    UserResponse,
    UserWithProfileRecord,
)


def user_document_to_record(document: Document) -> UserRecord:
    payload = dict(document)
    payload["id"] = document.doc_id
    return UserRecord(**payload)


def profile_document_to_record(document: Document) -> ProfileRecord:
    payload = dict(document)
    payload["id"] = document.doc_id
    return ProfileRecord(**payload)


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def _find_user_document_by_email(users_table, email: str) -> Document | None:
    normalized_email = email.strip().lower()
    for document in users_table.all():
        if str(document.get("email", "")).lower() == normalized_email:
            return document
    return None


def _find_profile_document_by_user_id(profiles_table, user_id: int) -> Document | None:
    for document in profiles_table.all():
        if int(document.get("user_id", -1)) == user_id:
            return document
    return None


def _get_profile_document_or_404(profiles_table, user_id: int) -> Document:
    profile_document = _find_profile_document_by_user_id(profiles_table, user_id)
    if profile_document is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile_document


def _build_user_with_profile_record(users_table, profiles_table, user_document: Document) -> UserWithProfileRecord:
    user_record = user_document_to_record(user_document)
    profile_document = _find_profile_document_by_user_id(profiles_table, user_record.id)

    if profile_document is None:
        return UserWithProfileRecord(**user_record.model_dump(), profile=None)

    profile_record = profile_document_to_record(profile_document)
    return UserWithProfileRecord(**user_record.model_dump(), profile=profile_record)


def _assert_unique_email_or_409(users_table, email: str, ignore_user_id: int | None = None) -> None:
    normalized_email = email.strip().lower()
    for document in users_table.all():
        if ignore_user_id is not None and document.doc_id == ignore_user_id:
            continue
        if str(document.get("email", "")).lower() == normalized_email:
            raise HTTPException(status_code=409, detail="A user with the same email already exists.")


def create_user(db_path: Path, payload: UserRegister) -> UserWithProfileRecord:
    hashed_password = _hash_password(payload.password)
    user_to_create = UserCreate(
        email=payload.email,
        hashed_password=hashed_password,
        is_active=payload.is_active,
        role=payload.role,
    )
    user = UserResponse(**user_to_create.model_dump())
    user_data = user.model_dump(mode="json")

    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")
        _assert_unique_email_or_409(users_table, user_data["email"])

        user_id = users_table.insert(user_data)
        created_user_document = users_table.get(doc_id=user_id)

        profile_data = ProfileResponse(
            user_id=user_id,
            name=payload.name,
            phone=payload.phone,
            address=payload.address,
        ).model_dump(mode="json")
        profiles_table.insert(profile_data)

        return _build_user_with_profile_record(users_table, profiles_table, created_user_document)


def get_user_by_id(db_path: Path, user_id: int) -> UserWithProfileRecord:
    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")
        user_document = users_table.get(doc_id=user_id)

        if user_document is None:
            raise HTTPException(status_code=404, detail="User not found.")

        return _build_user_with_profile_record(users_table, profiles_table, user_document)


def get_user_by_email(db_path: Path, email: str) -> UserWithProfileRecord:
    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")
        user_document = _find_user_document_by_email(users_table, email)

        if user_document is None:
            raise HTTPException(status_code=404, detail="User not found.")

        return _build_user_with_profile_record(users_table, profiles_table, user_document)


def update_user(db_path: Path, user_id: int, payload: UserCredentialsUpdate) -> UserWithProfileRecord:
    updates = payload.model_dump(exclude_unset=True)

    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")
        current_user_document = users_table.get(doc_id=user_id)

        if current_user_document is None:
            raise HTTPException(status_code=404, detail="User not found.")

        user_updates: dict[str, object] = {}

        if "email" in updates and updates["email"] is not None:
            _assert_unique_email_or_409(users_table, str(updates["email"]), ignore_user_id=user_id)
            user_updates["email"] = str(updates["email"]).lower()

        if "password" in updates and updates["password"] is not None:
            user_updates["hashed_password"] = _hash_password(str(updates["password"]))

        if "is_active" in updates and updates["is_active"] is not None:
            user_updates["is_active"] = bool(updates["is_active"])

        if "role" in updates and updates["role"] is not None:
            user_updates["role"] = str(updates["role"])

        if user_updates:
            merged_user = dict(current_user_document)
            merged_user.update(user_updates)
            validated_user = UserResponse(**merged_user).model_dump(mode="json")
            users_table.update(validated_user, doc_ids=[user_id])

        updated_user_document = users_table.get(doc_id=user_id)
        return _build_user_with_profile_record(users_table, profiles_table, updated_user_document)


def delete_user(db_path: Path, user_id: int) -> None:
    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")

        user_document = users_table.get(doc_id=user_id)
        if user_document is None:
            raise HTTPException(status_code=404, detail="User not found.")

        profile_document = _find_profile_document_by_user_id(profiles_table, user_id)
        if profile_document is not None:
            profiles_table.remove(doc_ids=[profile_document.doc_id])

        users_table.remove(doc_ids=[user_id])


def list_users(db_path: Path) -> list[UserWithProfileRecord]:
    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")
        documents = users_table.all()

        return [
            _build_user_with_profile_record(users_table, profiles_table, document)
            for document in documents
        ]


def get_profile_by_user_id(db_path: Path, user_id: int) -> ProfileRecord:
    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")

        user_document = users_table.get(doc_id=user_id)
        if user_document is None:
            raise HTTPException(status_code=404, detail="User not found.")

        profile_document = _get_profile_document_or_404(profiles_table, user_id)
        return profile_document_to_record(profile_document)


def update_profile_by_user_id(db_path: Path, user_id: int, payload: ProfileUpdate) -> ProfileRecord:
    updates = payload.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="At least one profile field must be provided.")

    with TinyDB(db_path) as db:
        users_table = db.table("users")
        profiles_table = db.table("profiles")

        user_document = users_table.get(doc_id=user_id)
        if user_document is None:
            raise HTTPException(status_code=404, detail="User not found.")

        profile_document = _get_profile_document_or_404(profiles_table, user_id)

        merged_profile = dict(profile_document)
        merged_profile.update(updates)
        validated_profile = ProfileResponse(**merged_profile).model_dump(mode="json")
        profiles_table.update(validated_profile, doc_ids=[profile_document.doc_id])

        updated_profile_document = profiles_table.get(doc_id=profile_document.doc_id)
        return profile_document_to_record(updated_profile_document)
