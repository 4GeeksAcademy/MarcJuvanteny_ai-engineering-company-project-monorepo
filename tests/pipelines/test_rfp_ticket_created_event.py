"""`process_rfp_ticket` anuncia el ticket (`rfp_ticket_created`,
`CONTEXT/CONTEXT10.md`) en el momento exacto en que el documento queda
clasificado como RFP válida -- al salir del nodo `classify`, ANTES de que
corran workers/synthesizer -- y nunca para un documento descartado.

Sin Postgres: el grafo, la conversión PDF y la sesión se sustituyen; lo que
se prueba es el orden real dentro de `pipeline.process_rfp_ticket`. El wire
SSE en sí se prueba en `tests/services/test_rfp_events_stream.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake import pipeline  # noqa: E402
from rfp_intake.models import RFPMetadataRecord, RFPTicket, TicketStatus  # noqa: E402


class _FakeSession:
    def __init__(self, ticket: RFPTicket):
        self.ticket = ticket

    def get(self, model, ticket_id):
        return self.ticket

    def add(self, obj):
        pass

    def commit(self):
        pass

    def close(self):
        pass


class _FakeGraph:
    """Emite los mismos estados acumulados que `stream_mode="values"`."""

    def __init__(self, log: list[str], *, is_valid: bool):
        self.log = log
        self.is_valid = is_valid

    def stream(self, initial_state, stream_mode):
        assert stream_mode == "values"
        state = dict(initial_state)
        yield state
        state = {
            **state,
            "classification": {"is_valid": self.is_valid, "reason": "test"},
            "metadata": {"client_name": "ModaViva", "client_country": "Spain", "services_requested": ["warehouse"]}
            if self.is_valid
            else None,
        }
        self.log.append("classify")
        yield state
        if not self.is_valid:
            return
        self.log.append("warehouse_worker")
        state = {**state, "warehouse_result": {"department_id": "warehouse"}}
        yield state
        self.log.append("synthesize")
        yield {**state, "summary": {"key_aspects_by_department": {}}}


def _run(monkeypatch, *, is_valid: bool) -> tuple[list[str], dict]:
    log: list[str] = []
    ticket = RFPTicket(id=7, status=TicketStatus.ANALIZANDO.value, raw_pdf_path="/tmp/x.pdf")

    def fake_announce(session, ticket_arg, metadata, readability_metrics):
        log.append(f"announce:{ticket_arg.status}:{metadata['client_name']}")
        return RFPMetadataRecord(id=1, ticket_id=ticket_arg.id, **metadata)

    monkeypatch.setattr(pipeline, "_COMPILED_GRAPH", _FakeGraph(log, is_valid=is_valid))
    monkeypatch.setattr(pipeline, "convert_pdf_to_markdown", lambda path: "# RFP")
    monkeypatch.setattr(pipeline, "compute_readability_metrics", lambda text: {})
    monkeypatch.setattr(pipeline, "_announce_valid_rfp", fake_announce)

    result = pipeline.process_rfp_ticket(7, session=_FakeSession(ticket))
    return log, result


def test_valid_rfp_is_announced_right_after_classify_and_before_workers(monkeypatch):
    log, result = _run(monkeypatch, is_valid=True)

    # Estado inicial del ticket en el evento = "analizando" (aún no analisis_completo).
    assert log == ["classify", "announce:analizando:ModaViva", "warehouse_worker", "synthesize"]
    assert result["status"] == TicketStatus.ANALISIS_COMPLETO.value


def test_discarded_document_is_never_announced(monkeypatch):
    log, result = _run(monkeypatch, is_valid=False)

    assert log == ["classify"]
    assert result["status"] == TicketStatus.DESCARTADO.value
