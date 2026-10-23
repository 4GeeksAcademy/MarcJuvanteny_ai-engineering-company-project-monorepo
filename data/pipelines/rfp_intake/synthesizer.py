"""Synthesizer (`CONTEXT/CONTEXT9.md`, "Orquestación por departamento"):
"El synthesizer consolida un resumen para Ventas (qué pedir a quién)."

Consolida los `WorkerResult` de todos los departamentos activos en un
resumen único -- el `key_aspects`/`reason`/`open_questions` que Ventas
necesita leer de un vistazo, y el payload de handoff que la Parte 2 recibe
(ver `CONTEXT9.md`, "Enrutamiento": "el handoff debe llevar `ticket_id` +
payload del synthesizer -- para que la Parte 2 arranque sin re-parsear el
PDF").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .departments import DEPARTMENTS
from .workers import WorkerResult


class DepartmentAsk(BaseModel):
    """Una entrada de "qué pedir a quién": a qué responsable preguntarle
    qué, para el departamento que le corresponde."""

    model_config = ConfigDict(extra="forbid")

    department_id: str
    department_name: str
    responsible: str
    questions: list[str]


class SynthesizedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    departments_needed: list[str]
    key_aspects_by_department: dict[str, dict]
    asks: list[DepartmentAsk]  # "qué pedir a quién" -- solo departamentos con preguntas abiertas


def synthesize(worker_results: list[WorkerResult]) -> SynthesizedSummary:
    key_aspects_by_department = {result.department_id: result.key_aspects for result in worker_results}

    asks = [
        DepartmentAsk(
            department_id=result.department_id,
            department_name=DEPARTMENTS[result.department_id].name,
            responsible=DEPARTMENTS[result.department_id].responsible,
            questions=result.open_questions,
        )
        for result in worker_results
        if result.open_questions
    ]

    return SynthesizedSummary(
        departments_needed=[result.department_id for result in worker_results],
        key_aspects_by_department=key_aspects_by_department,
        asks=asks,
    )
