"""Regresión de las correcciones críticas de la auditoría OWASP sobre
`services/incidents-api` (`Pasos/owasp-auditoria-hardening.md`).

Cada test reproduce el ataque contra la app REAL (`main.app`) por HTTP y
afirma que ahora se rechaza:

- C1 (A01/A04): `POST /users` con `"role": "admin"` sin token creaba un admin.
- C3 (A01): `GET /inventory/products|orders` y `GET /telemetry/report`
  respondían sin JWT (tracking_number, volúmenes, user_uuid de operarios).
- A02: contraseñas con sha256 de una pasada -> scrypt, con migración en login.
- A03/A01: el nombre del PDF subido a `/rfp/tickets` se concatenaba tal
  cual a la ruta de disco.

Correr con el venv del servicio:

    cd services/incidents-api && uv run --group dev pytest ../../tests/services -q
"""

from __future__ import annotations

import hashlib
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

os.environ.setdefault("SUPABASE_DATABASE_URL", "sqlite://")
os.environ["JWT_SECRET_KEY"] = "test-secret-owasp-incidents-32-bytes"
os.environ["TINYDB_PATH"] = str(Path(tempfile.mkdtemp()) / "users.json")

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from tinydb import TinyDB  # noqa: E402

import main  # noqa: E402
import routers.rfp as rfp_router  # noqa: E402
from auth_service import create_access_token  # noqa: E402
from database import get_db, get_tinydb_path  # noqa: E402
from models import SKU, StockEntry, StockExit, UserRegister, UserRole  # noqa: E402
from password_hashing import hash_password, needs_rehash, verify_password  # noqa: E402
from rfp_intake.models import RFPTicket  # noqa: E402
from user_service import create_user  # noqa: E402

client = TestClient(main.app)  # sin `with`: no corre el startup (Postgres real)


def _token_for(email: str, role: UserRole = UserRole.USER) -> str:
    user = create_user(get_tinydb_path(), UserRegister(email=email, password="Sup3rSecret!", role=role))
    token, _ = create_access_token(user.id, str(user.role))
    return token


@pytest.fixture(scope="module")
def user_token() -> str:
    return _token_for("operario.owasp@trackflow.test")


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _token_for("admin.owasp@trackflow.test", UserRole.ADMIN)


@pytest.fixture()
def sqlite_db():
    engine = create_engine(f"sqlite:///{tempfile.mkdtemp()}/inv.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine, tables=[SKU.__table__, StockEntry.__table__, StockExit.__table__])

    def override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[get_db] = override
    yield engine
    main.app.dependency_overrides.pop(get_db, None)


# --- C1: alta de usuarios con rol privilegiado --------------------------------------------


def test_anonymous_cannot_self_register_as_admin():
    response = client.post("/users", json={"email": "atacante@evil.test", "password": "12345678", "role": "admin"})

    assert response.status_code == 401
    with TinyDB(get_tinydb_path()) as db:
        assert not [u for u in db.table("users").all() if u["email"] == "atacante@evil.test"]


def test_non_admin_cannot_create_privileged_users(user_token):
    response = client.post(
        "/users",
        json={"email": "escalada@evil.test", "password": "12345678", "role": "manager"},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 403


def test_public_signup_still_works_for_the_base_role():
    response = client.post("/users", json={"email": "nuevo.operario@trackflow.test", "password": "12345678"})

    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_admin_can_still_create_privileged_users(admin_token):
    response = client.post(
        "/users",
        json={"email": "nuevo.manager@trackflow.test", "password": "12345678", "role": "manager"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "manager"


# --- C3: lecturas de tracking/inventario/telemetría sin JWT ---------------------------------


@pytest.mark.parametrize("path", ["/inventory/products", "/inventory/products/1", "/inventory/orders", "/telemetry/report"])
def test_reads_require_jwt(path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer basura"}).status_code == 401


def test_authenticated_reads_keep_working(sqlite_db, user_token):
    response = client.get("/inventory/orders", headers={"Authorization": f"Bearer {user_token}"})

    assert response.status_code == 200
    assert response.json() == []


# --- A02: hashing de contraseñas -------------------------------------------------------------


def test_new_passwords_use_scrypt_not_a_fast_hash():
    stored = hash_password("Sup3rSecret!")

    assert stored.startswith("scrypt$32768$8$1$")
    assert verify_password("Sup3rSecret!", stored)
    assert not verify_password("otra-clave", stored)
    assert not needs_rehash(stored)


def test_legacy_sha256_hash_is_upgraded_to_scrypt_on_login():
    salt = "abcd"
    legacy = f"sha256${salt}${hashlib.sha256(f'{salt}:Legacy123!'.encode()).hexdigest()}"
    with TinyDB(get_tinydb_path()) as db:
        db.table("users").insert(
            {"email": "legacy@trackflow.test", "hashed_password": legacy, "is_active": True, "role": "user"}
        )

    response = client.post("/auth/login", json={"email": "legacy@trackflow.test", "password": "Legacy123!"})

    assert response.status_code == 200
    with TinyDB(get_tinydb_path()) as db:
        stored = next(u for u in db.table("users").all() if u["email"] == "legacy@trackflow.test")["hashed_password"]
    assert stored.startswith("scrypt$")
    # y la misma contraseña sigue entrando con el hash nuevo
    assert client.post("/auth/login", json={"email": "legacy@trackflow.test", "password": "Legacy123!"}).status_code == 200


# --- A03/A01: nombre de archivo subido --------------------------------------------------------


def test_uploaded_filename_cannot_escape_the_upload_dir(monkeypatch, user_token, tmp_path):
    upload_dir = tmp_path / "raw"
    engine = create_engine(f"sqlite:///{tmp_path / 'rfp.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine, tables=[RFPTicket.__table__])
    monkeypatch.setattr(rfp_router, "RAW_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(rfp_router, "get_sql_engine", lambda: engine)
    monkeypatch.setattr(rfp_router.process_rfp_ticket_task, "delay", lambda ticket_id: None)

    response = client.post(
        "/rfp/tickets",
        files={"file": ("../../evil.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 202
    written = list(tmp_path.rglob("*evil.pdf"))
    assert len(written) == 1
    assert written[0].parent == upload_dir
