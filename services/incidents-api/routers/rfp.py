"""Endpoints HTTP de las 3 Partes de Hito 9 (`CONTEXT/CONTEXT9.md`: "Sin
API nuevo — extiende el backend existente en services/"). Capa fina: para
Partes 1-2 guarda/encola (Celery, trabajo pesado: PDF, LLM); para Parte 3
(aprobación humana) corre síncrono -- es solo una transición de estado de
grafo, sin trabajo pesado que encolar. Ningún nodo del pipeline, ninguna
lógica de agentes vive acá (`CONTEXT9.md`: "los routers importan y
disparan; no poseen la lógica de agentes").

Autenticado con el mismo mecanismo que el resto de este backend
(`auth_service.get_user_from_token`, mismo patrón que
`routers/inventory.py::get_current_inventory_user`) -- ningún checklist de
Hito 9 pide dejar esto sin auth, y es un endpoint de subida de archivos de
un proceso comercial interno, no un endpoint público.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_service import get_user_from_token
from database import get_tinydb_path
from models import UserWithProfileRecord

import rfp_pipeline_path  # noqa: F401
from pydantic import ValidationError
from rfp_intake.approval_graph import ApprovalDecision
from rfp_intake.models import RFPTicket, TicketStatus, get_sql_engine
from rfp_intake.pipeline import get_ticket_with_metadata, resume_department_approval, start_or_get_approval_round
from rfp_tasks import process_rfp_generation_task, process_rfp_ticket_task
from sqlmodel import Session, select

router = APIRouter(prefix="/rfp", tags=["rfp"])
bearer_scheme = HTTPBearer(auto_error=False)

ROOT_DIR = Path(__file__).resolve().parents[3]
RAW_UPLOAD_DIR = ROOT_DIR / "data" / "raw"


def get_current_rfp_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserWithProfileRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.", headers={"WWW-Authenticate": "Bearer"}
        )
    return get_user_from_token(get_tinydb_path(), credentials.credentials)


@router.post("/tickets", status_code=status.HTTP_202_ACCEPTED)
async def upload_rfp(
    file: UploadFile = File(...),
    current_user: UserWithProfileRecord = Depends(get_current_rfp_user),
) -> dict[str, Any]:
    _ = current_user

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Unsupported file type: the uploaded file must be a PDF.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    RAW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Auditoría OWASP A03/A01: solo el nombre base del archivo -- un
    # `filename` como "../../x.pdf" nunca puede salir de RAW_UPLOAD_DIR.
    stored_filename = f"{uuid.uuid4()}-{Path(file.filename).name}"
    stored_path = RAW_UPLOAD_DIR / stored_filename
    stored_path.write_bytes(content)

    with Session(get_sql_engine()) as session:
        ticket = RFPTicket(status=TicketStatus.ANALIZANDO.value, raw_pdf_path=str(stored_path))
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        ticket_id = ticket.id

    # Encola y responde de inmediato -- el pipeline (conversion, clasificacion,
    # orquestacion, workers, synthesizer, persistencia) corre en el worker de
    # Celery, nunca en este request (CONTEXT9.md: "el endpoint de subida
    # responde rapido; el pipeline corre en async").
    process_rfp_ticket_task.delay(ticket_id)

    return {"ticket_id": ticket_id, "status": TicketStatus.ANALIZANDO.value}


@router.get("/tickets/{ticket_id}")
async def get_rfp_ticket(
    ticket_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_rfp_user),
) -> dict[str, Any]:
    _ = current_user
    result = get_ticket_with_metadata(ticket_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return result


@router.post("/tickets/{ticket_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_rfp_sections(
    ticket_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_rfp_user),
) -> dict[str, Any]:
    """Hito 9 Parte 2 -- dispara generación + evaluación por departamento
    (ver `rfp_tasks.py::process_rfp_generation_task`) para un ticket que ya
    completó la Parte 1 (`analisis_completo`). Mismo patrón que
    `upload_rfp`: valida lo mínimo, encola, responde rápido -- la lógica de
    agentes vive en `rfp_intake.pipeline`, nunca acá."""

    _ = current_user
    with Session(get_sql_engine()) as session:
        ticket = session.get(RFPTicket, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        if ticket.status != TicketStatus.ANALISIS_COMPLETO.value:
            raise HTTPException(
                status_code=409,
                detail=f"Ticket is in status '{ticket.status}', expected '{TicketStatus.ANALISIS_COMPLETO.value}'.",
            )

    process_rfp_generation_task.delay(ticket_id)
    return {"ticket_id": ticket_id, "status": TicketStatus.ANALISIS_COMPLETO.value, "queued": True}


@router.post("/tickets/{ticket_id}/approval/start")
async def start_approval_round(
    ticket_id: int,
    current_user: UserWithProfileRecord = Depends(get_current_rfp_user),
) -> dict[str, Any]:
    """Hito 9 Parte 3 -- arranca (o simplemente devuelve, si ya está en
    curso) la ronda de aprobación humana por departamento para un ticket
    que ya completó la Parte 2. A diferencia de `generate_rfp_sections`,
    esto corre SÍNCRONO: no hay PDF que convertir ni LLM que esperar,
    solo transiciones de estado de un grafo determinista -- encolarlo en
    Celery sería indirección sin beneficio real."""

    _ = current_user
    try:
        return start_or_get_approval_round(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tickets/{ticket_id}/approval/{department_id}")
async def submit_department_approval(
    ticket_id: int,
    department_id: str,
    decision: ApprovalDecision,
    current_user: UserWithProfileRecord = Depends(get_current_rfp_user),
) -> dict[str, Any]:
    """Hito 9 Parte 3 -- `resume` explícito de UN departamento. `decision`
    ya llega validada por FastAPI/Pydantic vía `ApprovalDecision` (mismo
    modelo que usa el grafo, nunca duplicado) antes de que
    `resume_department_approval` construya el `Command(resume=...)`."""

    _ = current_user
    try:
        return resume_department_approval(ticket_id, department_id, decision.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tickets")
async def list_rfp_tickets(
    current_user: UserWithProfileRecord = Depends(get_current_rfp_user),
) -> list[dict[str, Any]]:
    _ = current_user
    with Session(get_sql_engine()) as session:
        tickets = session.exec(select(RFPTicket).order_by(RFPTicket.created_at.desc())).all()
        return [ticket.model_dump() for ticket in tickets]
