"""Pruebas de los workers de departamento y del grafo
orchestrator-worker-synthesizer (`CONTEXT/CONTEXT9.md`, checklist
"Pruebas": "...y para al menos un agente worker"). Corren con metadatos
sintéticos (sin depender de los PDF de muestra) para poder probar casos
límite -- volumen faltante, tasa de devolución faltante -- que los PDF
reales no necesariamente cubren todos a la vez.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.classifier import ClassificationResult, RFPMetadataExtraction  # noqa: E402
from rfp_intake.graph import build_graph  # noqa: E402
from rfp_intake.synthesizer import synthesize  # noqa: E402
from rfp_intake.workers import WorkerResult, run_reverse_worker, run_warehouse_worker  # noqa: E402


def _refuse_to_be_called(*args, **kwargs):
    raise AssertionError("esta funcion no deberia haberse llamado en este escenario")


# --- warehouse worker ------------------------------------------------------------------


def test_warehouse_worker_extracts_monthly_volume_when_present():
    metadata = RFPMetadataExtraction(client_country="USA", monthly_volume=5000, departments_needed=["warehouse"])

    result = run_warehouse_worker(metadata, "texto de la RFP, sin detalles extra.")

    assert result.department_id == "warehouse"
    assert result.key_aspects["monthly_volume"] == 5000
    assert result.open_questions == []


def test_warehouse_worker_asks_an_open_question_instead_of_inventing_volume():
    """"Nunca inventes... pedidos que no estén en la RFP": sin
    `monthly_volume`, el worker debe dejarlo fuera de `key_aspects` y
    agregar una pregunta abierta -- nunca un número a ojo."""

    metadata = RFPMetadataExtraction(client_country="Spain", monthly_volume=None)

    result = run_warehouse_worker(metadata, "texto sin volumen mencionado.")

    assert "monthly_volume" not in result.key_aspects
    assert any("volumen" in question.lower() for question in result.open_questions)


def test_warehouse_worker_extracts_peak_volume_context_when_mentioned():
    metadata = RFPMetadataExtraction(client_country="Spain", monthly_volume=3200)
    text = "picos estacionales de hasta 5.000 pedidos durante las campañas de enero."

    result = run_warehouse_worker(metadata, text)

    assert "peak_volume_context" in result.key_aspects


# --- reverse worker ----------------------------------------------------------------------


def test_reverse_worker_extracts_return_rate_when_present():
    metadata = RFPMetadataExtraction()
    text = "tiene una tasa de devolución elevada (aproximadamente 18% del volumen)."

    result = run_reverse_worker(metadata, text)

    assert result.key_aspects["estimated_return_rate_pct"] == 18


def test_reverse_worker_asks_about_missing_return_rate():
    metadata = RFPMetadataExtraction()

    result = run_reverse_worker(metadata, "el cliente pide gestión de devoluciones.")

    assert "estimated_return_rate_pct" not in result.key_aspects
    assert any("tasa" in q.lower() or "volumen" in q.lower() for q in result.open_questions)


# --- synthesizer -------------------------------------------------------------------------


def test_synthesizer_consolidates_results_and_lists_asks_by_responsible():
    results = [
        WorkerResult(department_id="warehouse", key_aspects={"monthly_volume": 3200}, open_questions=[]),
        WorkerResult(
            department_id="reverse",
            key_aspects={},
            open_questions=["¿Cuál es la tasa de devoluciones esperada?"],
        ),
    ]

    summary = synthesize(results)

    assert summary.departments_needed == ["warehouse", "reverse"]
    assert summary.key_aspects_by_department["warehouse"]["monthly_volume"] == 3200
    assert len(summary.asks) == 1
    assert summary.asks[0].department_id == "reverse"
    assert summary.asks[0].responsible == "Sofía Ramos"  # CONTEXT9.md Sección 2.1, no un nombre generico


# --- grafo orchestrator-worker-synthesizer: fan-out a SOLO los departamentos activos ----


def test_graph_discards_invalid_documents_without_calling_any_worker():
    compiled = build_graph(
        classify_fn=lambda text: ClassificationResult(is_valid=False, reason="no es una RFP"),
        extract_metadata_fn=_refuse_to_be_called,
        warehouse_worker_fn=_refuse_to_be_called,
        lastmile_worker_fn=_refuse_to_be_called,
        reverse_worker_fn=_refuse_to_be_called,
    )

    result = compiled.invoke({"markdown_text": "cualquier texto"})

    assert result["classification"]["is_valid"] is False
    assert result.get("metadata") is None
    assert result.get("summary") is None


def test_graph_only_calls_workers_for_departments_actually_needed():
    """ModaViva-like: solo warehouse + reverse -- lastmile NUNCA debe
    llamarse (igual que CONTEXT9.md Sección 4, caso 1)."""

    compiled = build_graph(
        classify_fn=lambda text: ClassificationResult(is_valid=True, reason="ok"),
        extract_metadata_fn=lambda text: RFPMetadataExtraction(
            client_country="Spain", departments_needed=["warehouse", "reverse"]
        ),
        lastmile_worker_fn=_refuse_to_be_called,
    )

    result = compiled.invoke({"markdown_text": "RFP de ejemplo"})

    assert result["warehouse_result"] is not None
    assert result["reverse_result"] is not None
    assert result.get("lastmile_result") is None
    assert set(result["summary"]["departments_needed"]) == {"warehouse", "reverse"}


def test_graph_runs_a_single_worker_when_only_one_department_is_needed():
    compiled = build_graph(
        classify_fn=lambda text: ClassificationResult(is_valid=True, reason="ok"),
        extract_metadata_fn=lambda text: RFPMetadataExtraction(client_country="USA", departments_needed=["warehouse"]),
        lastmile_worker_fn=_refuse_to_be_called,
        reverse_worker_fn=_refuse_to_be_called,
    )

    result = compiled.invoke({"markdown_text": "RFP de ejemplo"})

    assert result["warehouse_result"] is not None
    assert result.get("lastmile_result") is None
    assert result.get("reverse_result") is None
