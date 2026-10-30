"""Seguridad por diseño en `services/incidents-api` (Hito 12,
`Pasos/nist-seguridad-ia.md`):

- acciones irreversibles (borrar datos) con confirmación humana explícita:
  sin `X-Confirm-Action: delete-<recurso>:<id>` el DELETE no borra nada (428);
- credenciales: un `JWT_SECRET_KEY` corto se rechaza (fail-closed).

    cd services/incidents-api && uv run --group dev pytest ../../tests/services -q
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Corre con el venv de services/incidents-api; en otro venv se salta entero.
pytest.importorskip("tinydb")
pytest.importorskip("celery")

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "services" / "incidents-api"))
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

JWT_SECRET = "test-secret-secure-by-design-incidents-32b"
os.environ.setdefault("SUPABASE_DATABASE_URL", "sqlite://")
os.environ["JWT_SECRET_KEY"] = JWT_SECRET
os.environ.setdefault("TINYDB_PATH", str(Path(tempfile.mkdtemp()) / "users.json"))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tinydb import TinyDB  # noqa: E402

import main  # noqa: E402
from auth_service import create_access_token  # noqa: E402
from database import get_tinydb_path  # noqa: E402
from models import UserRegister, UserRole  # noqa: E402
from user_service import create_user  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    # Por test: otros módulos de tests/services fijan su propio secreto al importarse.
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)


def _auth(email: str, role: UserRole = UserRole.USER) -> tuple[int, dict[str, str]]:
    user = create_user(get_tinydb_path(), UserRegister(email=email, password="Sup3rSecret!", role=role))
    token, _ = create_access_token(user.id, str(user.role))
    return user.id, {"Authorization": f"Bearer {token}"}


def _insert_supplier(name: str) -> int:
    with TinyDB(get_tinydb_path()) as db:
        return db.table("suppliers").insert(
            {"name": name, "country": "spain", "categories": ["carrier"], "status": "active", "rate_per_shipment": 3.5}
        )


def _supplier_exists(supplier_id: int) -> bool:
    with TinyDB(get_tinydb_path()) as db:
        return db.table("suppliers").get(doc_id=supplier_id) is not None


# --- Acciones irreversibles: confirmación humana explícita ---------------------------------------


def test_delete_supplier_without_explicit_confirmation_deletes_nothing():
    _, headers = _auth("ops.confirm1@trackflow.test")
    supplier_id = _insert_supplier("MRW confirm 1")

    missing = client.delete(f"/suppliers/{supplier_id}", headers=headers)
    wrong_target = client.delete(
        f"/suppliers/{supplier_id}", headers={**headers, "X-Confirm-Action": f"delete-supplier:{supplier_id + 1}"}
    )

    assert missing.status_code == 428
    assert f"delete-supplier:{supplier_id}" in missing.json()["detail"]
    assert wrong_target.status_code == 428
    assert _supplier_exists(supplier_id)


def test_delete_supplier_with_explicit_confirmation():
    _, headers = _auth("ops.confirm2@trackflow.test")
    supplier_id = _insert_supplier("MRW confirm 2")

    response = client.delete(
        f"/suppliers/{supplier_id}", headers={**headers, "X-Confirm-Action": f"delete-supplier:{supplier_id}"}
    )

    assert response.status_code == 204
    assert not _supplier_exists(supplier_id)


def test_delete_user_requires_explicit_confirmation():
    user_id, headers = _auth("ops.confirm3@trackflow.test")

    assert client.delete(f"/users/{user_id}", headers=headers).status_code == 428
    with TinyDB(get_tinydb_path()) as db:
        assert db.table("users").get(doc_id=user_id) is not None

    confirmed = client.delete(f"/users/{user_id}", headers={**headers, "X-Confirm-Action": f"delete-user:{user_id}"})
    assert confirmed.status_code == 204


def test_confirmation_never_replaces_authentication():
    supplier_id = _insert_supplier("MRW confirm 4")

    response = client.delete(f"/suppliers/{supplier_id}", headers={"X-Confirm-Action": f"delete-supplier:{supplier_id}"})

    assert response.status_code == 401
    assert _supplier_exists(supplier_id)


# --- Credenciales -------------------------------------------------------------------------------


def test_short_jwt_secret_is_refused_fail_closed(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me")

    with pytest.raises(HTTPException) as refused:
        create_access_token(1, "user")

    assert refused.value.status_code == 500
    assert "32" in refused.value.detail
