"""CLI standalone del flujo de recepción de RFPs (`CONTEXT/CONTEXT9.md`,
"Layout del monorepo": "Scripts standalone (reproceso manual, smoke runs)
viven en `scripts/`, no como segundo HTTP API").

Dos modos:

  # Reprocesa un ticket existente (p. ej. uno que quedó en "analizando"
  # por un reinicio del worker de Celery a mitad de proceso):
  python scripts/rfp_reprocess.py --ticket-id 42

  # Smoke run: sube los 3 PDF de muestra de CONTEXT9.md Sección 4
  # (rfp-requests/trackflow/) como tickets nuevos, corre el pipeline
  # completo de forma SÍNCRONA (sin Celery) para cada uno, e imprime el
  # resultado -- útil para verificar el pipeline de punta a punta sin
  # levantar la API ni un worker.
  python scripts/rfp_reprocess.py --smoke

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

from rfp_intake.models import RFPTicket, TicketStatus, create_tables, get_sql_engine  # noqa: E402
from rfp_intake.pipeline import process_rfp_ticket  # noqa: E402
from sqlmodel import Session  # noqa: E402

SAMPLES_DIR = ROOT_DIR / "rfp-requests" / "trackflow"
RAW_DIR = ROOT_DIR / "data" / "raw"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket-id", type=int, help="Reprocesa un RFPTicket existente por su id.")
    group.add_argument("--smoke", action="store_true", help="Corre los 3 PDF de muestra de CONTEXT9.md de punta a punta.")
    args = parser.parse_args()

    if args.smoke:
        smoke_run()
    else:
        reprocess_ticket(args.ticket_id)


if __name__ == "__main__":
    main()
