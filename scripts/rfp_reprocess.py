"""CLI standalone del flujo de recepción de RFPs (`CONTEXT/CONTEXT9.md`,
"Layout del monorepo": "Scripts standalone (reproceso manual, smoke runs)
viven en `scripts/`, no como segundo HTTP API").

Tres modos:

  # Reprocesa un ticket existente (p. ej. uno que quedó en "analizando"
  # por un reinicio del worker de Celery a mitad de proceso):
  python scripts/rfp_reprocess.py --ticket-id 42

  # Smoke run (Parte 1 sola): sube los 3 PDF de muestra de CONTEXT9.md
  # Sección 4 (rfp-requests/trackflow/) como tickets nuevos, corre el
  # pipeline de recepción de forma SÍNCRONA (sin Celery) para cada uno, e
  # imprime el resultado -- útil para verificar la Parte 1 de punta a
  # punta sin levantar la API ni un worker.
  python scripts/rfp_reprocess.py --smoke

  # E2E smoke run (Hito 9 Parte 3, checklist "Revisión de extremo a
  # extremo": "Entrega una ruta E2E reproducible: fixture + script o test
  # de integración que ejecute la Parte 3 con aprobaciones simuladas
  # (resume programático o equivalente) -- la revisión no debe depender
  # solo de clicks irreproducibles en la UI"): sube
  # `trackflow-request-1.pdf` (ModaViva) como ticket nuevo y lo corre de
  # punta a punta a través de las 3 Partes completas -- recepción →
  # generación → aprobación y cierre -- con aprobaciones SIMULADAS
  # (`resume_department_approval(..., {"decision": "approve"})`
  # programático, nunca un click de UI), verificando en cada paso que el
  # estado/los datos se mantienen consistentes (aserciones reales, no solo
  # impresiones).
  python scripts/rfp_reprocess.py --e2e-smoke

Nunca llama a `services/incidents-api` por HTTP -- importa
`data/pipelines/rfp_intake` directamente, igual que haría el router o la
tarea Celery (mismo motivo que la guía: esto no es "un segundo HTTP API").
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.models import (  # noqa: E402
    RFPTicket,
    TicketStatus,
    create_tables,
    get_sql_engine,
)
from rfp_intake.pipeline import (  # noqa: E402
    get_ticket_with_metadata,
    process_rfp_generation,
    process_rfp_ticket,
    resume_department_approval,
    start_or_get_approval_round,
)
from sqlmodel import Session  # noqa: E402

SAMPLES_DIR = ROOT_DIR / "rfp-requests" / "trackflow"
RAW_DIR = ROOT_DIR / "data" / "raw"

# Tope de rondas de aprobación simuladas -- cada ronda "aprueba" todo lo
# pendiente; si el arbitraje reabre algún departamento, hace falta otra
# ronda. Acotado para que el script nunca cuelgue si algo queda mal
# resuelto -- consistente con el límite de iteraciones real del grafo
# (`approval_graph.MAX_ARBITRATION_ROUNDS`).
MAX_E2E_APPROVAL_ROUNDS = 5


def reprocess_ticket(ticket_id: int) -> None:
    result = process_rfp_ticket(ticket_id)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


def smoke_run() -> None:
    create_tables()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    sample_pdfs = sorted(SAMPLES_DIR.glob("trackflow-request-*.pdf"))
    if not sample_pdfs:
        print(f"No hay PDF de muestra en {SAMPLES_DIR} -- correr "
              f"data/pipelines/rfp_intake/_generate_sample_pdfs.py primero.")
        return

    for pdf_path in sample_pdfs:
        dest = RAW_DIR / f"smoke-{pdf_path.name}"
        dest.write_bytes(pdf_path.read_bytes())

        with Session(get_sql_engine()) as session:
            ticket = RFPTicket(status=TicketStatus.ANALIZANDO.value, raw_pdf_path=str(dest))
            session.add(ticket)
            session.commit()
            session.refresh(ticket)
            ticket_id = ticket.id

        print(f"=== {pdf_path.name} -> ticket {ticket_id} ===")
        result = process_rfp_ticket(ticket_id)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        print()


def _create_ticket_from_sample(pdf_name: str) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = SAMPLES_DIR / pdf_name
    dest = RAW_DIR / f"e2e-smoke-{pdf_name}"
    dest.write_bytes(pdf_path.read_bytes())

    with Session(get_sql_engine()) as session:
        ticket = RFPTicket(status=TicketStatus.ANALIZANDO.value, raw_pdf_path=str(dest))
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return ticket.id


def e2e_smoke_run() -> None:
    """Ver docstring del módulo -- Parte 1 -> Parte 2 -> Parte 3 con
    aprobaciones simuladas, con aserciones de consistencia en cada
    transición (nunca solo `print`)."""

    create_tables()

    ticket_id = _create_ticket_from_sample("trackflow-request-1.pdf")
    print(f"=== E2E smoke: ticket {ticket_id} (ModaViva, trackflow-request-1.pdf) ===\n")

    # --- Parte 1: recepción, clasificación, enrutamiento por departamento ---
    print("--- Parte 1: process_rfp_ticket ---")
    part1_result = process_rfp_ticket(ticket_id)
    print(json.dumps(part1_result, indent=2, ensure_ascii=False, default=str))
    assert part1_result["status"] == TicketStatus.ANALISIS_COMPLETO.value, (
        f"Parte 1 debía terminar en '{TicketStatus.ANALISIS_COMPLETO.value}', terminó en '{part1_result['status']}'."
    )
    assert set(part1_result["metadata"]["departments_needed"]) == {"warehouse", "reverse"}, (
        "ModaViva (CONTEXT9.md §4, caso 1) debe activar warehouse+reverse, nunca lastmile."
    )

    # --- Parte 2: generación por departamento + evaluación/ciclo generador-evaluador ---
    print("\n--- Parte 2: process_rfp_generation ---")
    part2_result = process_rfp_generation(ticket_id)
    print(json.dumps(part2_result, indent=2, ensure_ascii=False, default=str))
    assert part2_result["status"] in (TicketStatus.EN_EVALUACION.value, TicketStatus.NEEDS_HUMAN_REVIEW.value), (
        f"Parte 2 debía terminar en 'en_evaluación' o 'needs_human_review', terminó en '{part2_result['status']}'."
    )
    assert set(part2_result["evaluations"]) == {"warehouse", "reverse"}, (
        "La Parte 2 debe evaluar EXACTAMENTE los departamentos que la Parte 1 marcó como activos -- "
        "ningún salto/pérdida de departamento entre partes."
    )

    # --- Parte 3: aprobación humana por departamento (SIMULADA) + arbitraje + cierre ---
    print("\n--- Parte 3: start_or_get_approval_round ---")
    approval_state = start_or_get_approval_round(ticket_id)
    print(json.dumps(approval_state, indent=2, ensure_ascii=False, default=str))
    assert approval_state["status"] == TicketStatus.ESPERANDO_APROBACION.value
    assert {p["department_id"] for p in approval_state["pending_approvals"]} == {"warehouse", "reverse"}, (
        "La ronda de aprobación debe pedir decisión para los MISMOS departamentos activos de las Partes 1-2 -- "
        "ningún dato perdido en la transición."
    )

    for round_number in range(1, MAX_E2E_APPROVAL_ROUNDS + 1):
        pending = {p["department_id"] for p in approval_state["pending_approvals"]}
        if not pending:
            break
        print(f"\n--- Parte 3: ronda de aprobación simulada {round_number} -- aprobando {sorted(pending)} ---")
        for department_id in pending:
            approval_state = resume_department_approval(ticket_id, department_id, {"decision": "approve"})
        print(f"status tras la ronda {round_number}: {approval_state['status']}")

    assert approval_state["status"] == TicketStatus.TERMINADO.value, (
        f"La Parte 3 no cerró el ticket en {MAX_E2E_APPROVAL_ROUNDS} rondas de aprobación simuladas "
        f"(quedó en '{approval_state['status']}') -- revisar el log de arbitraje arriba."
    )
    assert approval_state["final_document"] is not None, "terminado sin FinalDocument -- inconsistencia real."

    # --- Verificación final de consistencia de punta a punta ---
    full_ticket = get_ticket_with_metadata(ticket_id)
    assert full_ticket["ticket"]["status"] == TicketStatus.TERMINADO.value
    assert full_ticket["final_document"] is not None
    for section in full_ticket["sections"]:
        assert section["approval_status"] == "approved", (
            f"Sección '{section['department_id']}' no quedó 'approved' pese a que el ticket está 'terminado' -- "
            "inconsistencia real entre RFPTicket y RFPDepartmentSection."
        )

    print(f"\n=== E2E smoke OK: ticket {ticket_id} terminó en 'terminado' con FinalDocument real, "
          f"estado consistente de punta a punta a través de las 3 Partes. ===")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket-id", type=int, help="Reprocesa un RFPTicket existente por su id.")
    group.add_argument("--smoke", action="store_true", help="Corre los 3 PDF de muestra de CONTEXT9.md de punta a punta (solo Parte 1).")
    group.add_argument(
        "--e2e-smoke", action="store_true",
        help="Corre 1 RFP de punta a punta a través de las 3 Partes completas, con aprobaciones simuladas (Hito 9 Parte 3).",
    )
    args = parser.parse_args()

    if args.smoke:
        smoke_run()
    elif args.e2e_smoke:
        e2e_smoke_run()
    else:
        reprocess_ticket(args.ticket_id)


if __name__ == "__main__":
    main()
