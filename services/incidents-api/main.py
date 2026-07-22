from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from tinydb import TinyDB
from tinydb.table import Document

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from incident_analysis import CSVInputError, read_csv_text, summarize_rows, summary_to_csv_text
from models import (
    SupplierCreate,
    SupplierRateUpdate,
    SupplierRecord,
    SupplierResponse,
    SupplierStatusUpdate,
    VALID_CATEGORIES,
    VALID_COUNTRIES,
)

app = FastAPI(title="Incidents API", version="0.1.0")
LAST_ANALYSIS_SUMMARY: dict[str, Any] | None = None
DEFAULT_SUPPLIERS_DB_PATH = Path(__file__).resolve().parent / "suppliers.json"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def get_suppliers_db_path() -> Path:
    raw_path = os.environ.get("TINYDB_PATH")
    return Path(raw_path) if raw_path else DEFAULT_SUPPLIERS_DB_PATH


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
async def create_supplier(payload: SupplierCreate) -> SupplierRecord:
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
) -> list[SupplierRecord]:
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
async def get_supplier(supplier_id: int) -> SupplierRecord:
    document = get_supplier_document_or_404(supplier_id)
    return supplier_document_to_record(document)


@app.patch("/suppliers/{supplier_id}/rate", response_model=SupplierRecord)
async def update_supplier_rate(supplier_id: int, payload: SupplierRateUpdate) -> SupplierRecord:
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
async def update_supplier_status(supplier_id: int, payload: SupplierStatusUpdate) -> SupplierRecord:
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
async def delete_supplier(supplier_id: int) -> Response:
    get_supplier_document_or_404(supplier_id)

    with TinyDB(get_suppliers_db_path()) as db:
        suppliers_table = db.table("suppliers")
        suppliers_table.remove(doc_ids=[supplier_id])

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/incidents/analyze")
async def analyze_incidents_csv(file: UploadFile = File(...)) -> dict[str, Any]:
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
async def export_last_analysis_results() -> Response:
    if LAST_ANALYSIS_SUMMARY is None:
        raise HTTPException(status_code=404, detail="No analysis results available yet.")

    return Response(
        content=summary_to_csv_text(LAST_ANALYSIS_SUMMARY),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )
