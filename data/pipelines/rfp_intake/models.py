"""Entidades persistentes del flujo de recepción de RFPs (`CONTEXT/CONTEXT9.md`,
Hito 9 Parte 1, Sección 2.3: "Persiste Ticket, metadatos RFP y
DepartmentSection.key_aspects en PostgreSQL (Supabase) vía tu capa
SQLModel/DB existente -- TinyDB no es aceptable para estos datos").

Motor de base de datos propio de `data/pipelines` (mismo `SUPABASE_DATABASE_URL`
que `services/incidents-api`, ver `.env.example` -- "misma base que
services/incidents-api"), no una reutilización cruzada del motor de
`services/incidents-api/database.py`: `data/pipelines` es el paquete de
base del monorepo (del que los `services/*` importan), nunca al revés --
mismo patrón que `exec_weekly_inventory_kpis` ya usa para escribir a
Postgres de forma independiente.

`FinalDocument` y `RFPNodeTrace` (Hito 9 Parte 3, "Cierre del documento" y
"Guardrails y control de flujo" -- trazabilidad por ejecución de nodo) se
agregan en esta entrega.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, create_engine

PACKAGE_DIR = Path(__file__).resolve().parent.parent  # data/pipelines/ -- env compartido, ver docstring
load_dotenv(PACKAGE_DIR / ".env")


class TicketStatus(StrEnum):
    """Tabla "Estado del ticket por parte" de `CONTEXT9.md` Sección 2.3 --
    el enum completo de las 3 partes vive acá desde ahora (es la máquina de
    estados real del ticket), aunque esta entrega solo produce los
    primeros tres valores."""

    ANALIZANDO = "analizando"
    DESCARTADO = "descartado"
    ANALISIS_COMPLETO = "analisis_completo"
    GENERANDO_BORRADOR = "generando_borrador"
    EN_EVALUACION = "en_evaluación"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    ESPERANDO_APROBACION = "esperando_aprobación"
    TERMINADO = "terminado"


# `department_id` válidos (CONTEXT9.md Sección 2.1) -- usados tanto por
# RFPTicket.departments_needed como por RFPDepartmentSection.department_id.
VALID_DEPARTMENT_IDS = ("warehouse", "lastmile", "reverse")
VALID_CLIENT_COUNTRIES = ("USA", "Spain")


class RFPTicket(SQLModel, table=True):
    __tablename__ = "rfp_tickets"

    id: int | None = SQLField(default=None, primary_key=True)
    status: str = SQLField(default=TicketStatus.ANALIZANDO.value, index=True)
    raw_pdf_path: str
    discard_reason: str | None = None
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class RFPMetadataRecord(SQLModel, table=True):
    """Uno por ticket (relación 1:1) -- metadatos extraídos del documento
    convertido, nunca inventados (`CONTEXT9.md`: "nunca inventes
    pallets/SKU/pedidos que no estén en la RFP")."""

    __tablename__ = "rfp_metadata"

    id: int | None = SQLField(default=None, primary_key=True)
    ticket_id: int = SQLField(foreign_key="rfp_tickets.id", index=True, unique=True)
    client_name: str | None = None
    client_country: str | None = None  # "USA" | "Spain" -- ver VALID_CLIENT_COUNTRIES
    services_requested: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    monthly_volume: int | None = None
    deadline: str | None = None
    budget_range: str | None = None
    departments_needed: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    readability_metrics: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSONB, nullable=False))


class RFPDepartmentSection(SQLModel, table=True):
    """Uno por `(ticket_id, department_id)`. `key_aspects` lo llena la
    Parte 1; `draft_content`/`evaluation_results` la Parte 2 (que también
    usa `approval_status="needs_human_review"` cuando se agota el límite
    de iteraciones del ciclo generador-evaluador). La Parte 3 vuelve a
    escribir `approval_status` con la decisión real
    (`"approved"`/`"rejected_final"`/`"pending"`) + `approver` (el
    responsable fijo de `departments.py`) + `approved_at` cuando
    corresponde."""

    __tablename__ = "rfp_department_sections"

    id: int | None = SQLField(default=None, primary_key=True)
    ticket_id: int = SQLField(foreign_key="rfp_tickets.id", index=True)
    department_id: str
    key_aspects: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    draft_content: str | None = None
    evaluation_results: dict[str, Any] | None = SQLField(default=None, sa_column=Column(JSONB))
    approval_status: str | None = None
    approver: str | None = None
    approved_at: datetime | None = None


class FinalDocument(SQLModel, table=True):
    """`CONTEXT9.md` Sección 2.3 -- uno por ticket (1:1), generado solo
    cuando TODOS los `departments_needed` terminan en `approval_status ==
    "approved"` (`pipeline.py::process_rfp_approval`). `sections` es un
    snapshot de los `draft_content` aprobados en el momento del cierre
    (no una referencia viva a `RFPDepartmentSection` -- el documento final
    no debe cambiar si alguien edita una sección después)."""

    __tablename__ = "rfp_final_documents"

    id: int | None = SQLField(default=None, primary_key=True)
    ticket_id: int = SQLField(foreign_key="rfp_tickets.id", index=True, unique=True)
    sections: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    currency: str
    generated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class RFPNodeTrace(SQLModel, table=True):
    """Hito 9 Parte 3, "Guardrails y control de flujo": "Registra en el
    estado, para cada ejecución de nodo, el agente, el input, el output y
    el timestamp (trazabilidad)". Se persiste en Postgres (no solo en el
    estado efímero de LangGraph) para que la traza sobreviva más allá de
    una ejecución del grafo y sea consultable (`GET
    /rfp/tickets/{id}/trace`) -- append-only, nunca se actualiza una fila
    existente."""

    __tablename__ = "rfp_node_traces"

    id: int | None = SQLField(default=None, primary_key=True)
    ticket_id: int = SQLField(foreign_key="rfp_tickets.id", index=True)
    department_id: str | None = None
    node_name: str
    agent: str
    input: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    output: dict[str, Any] | None = SQLField(default=None, sa_column=Column(JSONB))
    timestamp: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


def get_rfp_database_url() -> str:
    database_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_DATABASE_URL (or DATABASE_URL) is not configured.")
    return database_url


@lru_cache(maxsize=1)
def get_sql_engine():
    return create_engine(get_rfp_database_url(), pool_pre_ping=True)


def get_session() -> Generator[Session, None, None]:
    with Session(get_sql_engine()) as session:
        yield session


def create_tables() -> None:
    """Crea las tablas si no existen -- equivalente de `CONTEXT9.md` al
    `SQLModel.metadata.create_all()` que `services/incidents-api/main.py`
    ya corre en su propio startup, pero acotado a las tablas de este
    módulo (`SQLModel.metadata.create_all()` sin filtro crearía también las
    tablas de `services/incidents-api/models.py` si ambos módulos
    comparten el registro de metadata del proceso que lo ejecuta -- acá se
    pasa `tables=` explícito para evitar ese efecto secundario)."""

    SQLModel.metadata.create_all(
        get_sql_engine(),
        tables=[
            RFPTicket.__table__,
            RFPMetadataRecord.__table__,
            RFPDepartmentSection.__table__,
            FinalDocument.__table__,
            RFPNodeTrace.__table__,
        ],
    )
