from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from tinydb import TinyDB
from tinydb.table import Document

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from auth_service import authenticate_user, create_access_token, get_user_from_token
from incident_analysis import CSVInputError, read_csv_text, summarize_rows, summary_to_csv_text
from models import (
    AuthMeProfile,
    AuthMeResponse,
    LoginRequest,
    SupplierCreate,
    ProfileRecord,
    ProfileUpdate,
    SupplierRateUpdate,
    SupplierRecord,
    SupplierResponse,
    SupplierStatusUpdate,
    TokenResponse,
    UserCredentialsUpdate,
    UserRegister,
    UserRole,
    UserWithProfileRecord,
    VALID_CATEGORIES,
    VALID_COUNTRIES,
)
from user_service import (
    create_user as create_user_service,
    delete_user as delete_user_service,
    get_profile_by_user_id,
    get_user_by_email,
    get_user_by_id,
    list_users as list_users_service,
    update_profile_by_user_id,
    update_user as update_user_service,
)

app = FastAPI(title="Incidents API", version="0.1.0")
LAST_ANALYSIS_SUMMARY: dict[str, Any] | None = None
DEFAULT_SUPPLIERS_DB_PATH = Path(__file__).resolve().parent / "suppliers.json"
bearer_scheme = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def get_suppliers_db_path() -> Path:
    raw_path = os.environ.get("TINYDB_PATH")
    return Path(raw_path) if raw_path else DEFAULT_SUPPLIERS_DB_PATH


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserWithProfileRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_user_from_token(get_suppliers_db_path(), credentials.credentials)


def ensure_self_or_admin(actor: UserWithProfileRecord, user_id: int) -> None:
    if actor.id != user_id and actor.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only the same user or an admin can perform this action.")


def supplier_document_to_record(document: Document) -> SupplierRecord:
    payload = dict(document)
    payload["id"] = document.doc_id
    return SupplierRecord(**payload)


def get_supplier_document_or_404(supplier_id: int) -> Document:
    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        document = suppliers_table.get(doc_id=supplier_id)

    if document is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    return document


def validate_supplier_filters(country: str | None, category: str | None) -> None:
    if country is not None and country not in VALID_COUNTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"country must be one of: {VALID_COUNTRIES}",
        )

    if category is not None and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of: {VALID_CATEGORIES}",
        )


@app.post("/suppliers", response_model=SupplierRecord, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> SupplierRecord:
    _ = current_user
    supplier = SupplierResponse(**payload.model_dump())
    supplier_data = supplier.model_dump(mode="json")

    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        for document in suppliers_table.all():
            if document.get("name") == supplier_data["name"] and document.get("country") == supplier_data["country"]:
                raise HTTPException(
                    status_code=409,
                    detail="A supplier with the same name and country already exists.",
                )

        doc_id = suppliers_table.insert(supplier_data)
        created_document = suppliers_table.get(doc_id=doc_id)

    return supplier_document_to_record(created_document)


@app.get("/suppliers", response_model=list[SupplierRecord])
async def list_suppliers(
    country: str | None = Query(default=None),
    category: str | None = Query(default=None),
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> list[SupplierRecord]:
    _ = current_user
    validate_supplier_filters(country, category)

    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        documents = suppliers_table.all()

    filtered_documents: list[Document] = []
    for document in documents:
        if country is not None and document.get("country") != country:
            continue
        if category is not None and category not in document.get("categories", []):
            continue
        filtered_documents.append(document)

    return [supplier_document_to_record(document) for document in filtered_documents]


@app.get("/suppliers/{supplier_id}", response_model=SupplierRecord)
async def get_supplier(
    supplier_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> SupplierRecord:
    _ = current_user
    document = get_supplier_document_or_404(supplier_id)
    return supplier_document_to_record(document)


@app.patch("/suppliers/{supplier_id}/rate", response_model=SupplierRecord)
async def update_supplier_rate(
    supplier_id: int,
    payload: SupplierRateUpdate,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> SupplierRecord:
    _ = current_user
    get_supplier_document_or_404(supplier_id)
    updated_at = datetime.now(timezone.utc).isoformat()

    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        suppliers_table.update(
            {
                "rate_per_shipment": float(payload.rate_per_shipment),
                "updated_at": updated_at,
            },
            doc_ids=[supplier_id],
        )
        updated_document = suppliers_table.get(doc_id=supplier_id)

    return supplier_document_to_record(updated_document)


@app.patch("/suppliers/{supplier_id}/status", response_model=SupplierRecord)
async def update_supplier_status(
    supplier_id: int,
    payload: SupplierStatusUpdate,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> SupplierRecord:
    _ = current_user
    get_supplier_document_or_404(supplier_id)

    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        suppliers_table.update(
            {"status": payload.status.value},
            doc_ids=[supplier_id],
        )
        updated_document = suppliers_table.get(doc_id=supplier_id)

    return supplier_document_to_record(updated_document)


@app.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> Response:
    _ = current_user
    get_supplier_document_or_404(supplier_id)

    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        suppliers_table.remove(doc_ids=[supplier_id])

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/users", response_model=UserWithProfileRecord, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserRegister) -> UserWithProfileRecord:
    return create_user_service(get_suppliers_db_path(), payload)


@app.get("/users", response_model=list[UserWithProfileRecord])
async def list_users(current_user: UserWithProfileRecord = Depends(get_current_user)) -> list[UserWithProfileRecord]:
    _ = current_user
    return list_users_service(get_suppliers_db_path())


@app.get("/users/by-email", response_model=UserWithProfileRecord)
async def get_user_by_email_route(
    email: str = Query(..., min_length=5),
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> UserWithProfileRecord:
    _ = current_user
    return get_user_by_email(get_suppliers_db_path(), email)


@app.get("/users/{user_id}", response_model=UserWithProfileRecord)
async def get_user(
    user_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> UserWithProfileRecord:
    ensure_self_or_admin(current_user, user_id)
    return get_user_by_id(get_suppliers_db_path(), user_id)


@app.put("/users/{user_id}", response_model=UserWithProfileRecord)
async def update_user(
    user_id: int,
    payload: UserCredentialsUpdate,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> UserWithProfileRecord:
    ensure_self_or_admin(current_user, user_id)

    if payload.role is not None and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can update role.")

    if payload.is_active is not None and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can update is_active.")

    return update_user_service(get_suppliers_db_path(), user_id, payload)


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> Response:
    ensure_self_or_admin(current_user, user_id)
    delete_user_service(get_suppliers_db_path(), user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/profiles/me", response_model=ProfileRecord)
async def get_my_profile(current_user: UserWithProfileRecord = Depends(get_current_user)) -> ProfileRecord:
    return get_profile_by_user_id(get_suppliers_db_path(), current_user.id)


@app.put("/profiles/me", response_model=ProfileRecord)
async def update_my_profile(
    payload: ProfileUpdate,
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> ProfileRecord:
    return update_profile_by_user_id(get_suppliers_db_path(), current_user.id, payload)


@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = authenticate_user(get_suppliers_db_path(), payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_minutes = create_access_token(user.id, str(user.role))
    return TokenResponse(access_token=access_token, expires_in=expires_minutes * 60)


@app.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(current_user: UserWithProfileRecord = Depends(get_current_user)) -> AuthMeResponse:
    profile_payload = None
    if current_user.profile is not None:
        profile_payload = AuthMeProfile(
            name=current_user.profile.name,
            phone=current_user.profile.phone,
            address=current_user.profile.address,
        )

    return AuthMeResponse(
        email=current_user.email,
        role=current_user.role,
        profile=profile_payload,
    )


@app.post("/api/incidents/analyze")
async def analyze_incidents_csv(
    file: UploadFile = File(...),
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> dict[str, Any]:
    _ = current_user
    global LAST_ANALYSIS_SUMMARY

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type: the uploaded file must use the .csv extension.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file encoding: CSV must be UTF-8 encoded.",
        ) from exc

    try:
        rows = read_csv_text(text)
    except CSVInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    LAST_ANALYSIS_SUMMARY = summarize_rows(rows)
    return LAST_ANALYSIS_SUMMARY


@app.get("/api/incidents/results/export")
async def export_last_analysis_results(
    current_user: UserWithProfileRecord = Depends(get_current_user),
) -> Response:
    _ = current_user
    if LAST_ANALYSIS_SUMMARY is None:
        raise HTTPException(status_code=404, detail="No analysis results available yet.")

    return Response(
        content=summary_to_csv_text(LAST_ANALYSIS_SUMMARY),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )
