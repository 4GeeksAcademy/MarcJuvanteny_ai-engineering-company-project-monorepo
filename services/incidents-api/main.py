from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from incident_analysis import CSVInputError, read_csv_text, summarize_rows, summary_to_csv_text

app = FastAPI(title="Incidents API", version="0.1.0")
LAST_ANALYSIS_SUMMARY: dict[str, Any] | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
