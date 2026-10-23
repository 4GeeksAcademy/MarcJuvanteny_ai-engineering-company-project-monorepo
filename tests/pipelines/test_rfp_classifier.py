"""Pruebas del agente clasificador y de la extracción de metadatos
(`CONTEXT/CONTEXT9.md`, Hito 9 Parte 1, checklist "Pruebas": "Incluye
pruebas unitarias en `tests/pipelines/` para el agente clasificador").

Corren contra el Markdown REAL de los 3 PDF de muestra de `CONTEXT9.md`
Sección 4 (`rfp-requests/trackflow/trackflow-request-{1,2,3}.pdf`,
generados porque no venían en este repo -- ver
`Pasos/rfp-intake-fase1.md`), convertidos una sola vez por módulo con
MarkItDown real -- nunca texto inventado a mano.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.classifier import classify_rfp, extract_metadata  # noqa: E402
from rfp_intake.pdf_conversion import convert_pdf_to_markdown  # noqa: E402

SAMPLES_DIR = ROOT_DIR / "rfp-requests" / "trackflow"


def _markdown_for(filename: str) -> str:
    path = SAMPLES_DIR / filename
    if not path.exists():
        pytest.skip(f"{path} no existe -- correr data/pipelines/rfp_intake/_generate_sample_pdfs.py primero.")
    return convert_pdf_to_markdown(path)


@pytest.fixture(scope="module")
def formal_rfp_markdown() -> str:
    """trackflow-request-1.pdf: ModaViva (España), warehouse+reverse, aceptar."""
    return _markdown_for("trackflow-request-1.pdf")


@pytest.fixture(scope="module")
def informal_rfp_markdown() -> str:
    """trackflow-request-2.pdf: Luna Cosmetics (LA), warehouse+lastmile, aceptar."""
    return _markdown_for("trackflow-request-2.pdf")


@pytest.fixture(scope="module")
def invalid_document_markdown() -> str:
    """trackflow-request-3.pdf: pitch de tarifas de carrier, rechazar."""
    return _markdown_for("trackflow-request-3.pdf")


# --- Clasificación: los 3 casos obligatorios de CONTEXT9.md Sección 4 --------------


def test_eval_formal_rfp_is_accepted(formal_rfp_markdown: str):
    result = classify_rfp(formal_rfp_markdown)
    assert result.is_valid is True


def test_eval_informal_rfp_is_accepted(informal_rfp_markdown: str):
    result = classify_rfp(informal_rfp_markdown)
    assert result.is_valid is True


def test_eval_invalid_document_is_rejected_with_a_reason():
    """"No falles en silencio": el rechazo siempre trae un motivo legible,
    nunca `is_valid=False` sin explicación."""

    md = _markdown_for("trackflow-request-3.pdf")
    result = classify_rfp(md)
    assert result.is_valid is False
    assert result.reason  # nunca un string vacio


def test_classifier_does_not_confuse_a_carrier_pitch_with_a_real_rfp_just_because_it_mentions_logistics():
    """El documento inválido SÍ menciona "last-mile delivery network" y
    tarifas -- el clasificador no debe aprobarlo solo por tener vocabulario
    de logística; la señal real es quién le pide qué a quién."""

    md = _markdown_for("trackflow-request-3.pdf")
    result = classify_rfp(md)
    assert result.is_valid is False


# --- Extracción de metadatos: valores EXACTOS que especifica CONTEXT9.md -----------


def test_eval_formal_rfp_metadata_matches_the_briefing_exactly(formal_rfp_markdown: str):
    """`CONTEXT9.md` Sección 4, caso 1: ModaViva (España), solo
    almacenamiento + devoluciones -- activa warehouse y reverse, NO
    lastmile. Moneda: EUR (implícita en client_country=Spain)."""

    metadata = extract_metadata(formal_rfp_markdown)

    assert metadata.client_country == "Spain"
    assert set(metadata.departments_needed) == {"warehouse", "reverse"}
    assert "lastmile" not in metadata.departments_needed
    assert metadata.monthly_volume == 3200


def test_eval_informal_rfp_metadata_matches_the_briefing_exactly(informal_rfp_markdown: str):
    """`CONTEXT9.md` Sección 4, caso 2: Luna Cosmetics (LA), almacenamiento
    + última milla EE. UU., ~5.000 pedidos/mes -- activa warehouse y
    lastmile, NO reverse."""

    metadata = extract_metadata(informal_rfp_markdown)

    assert metadata.client_country == "USA"
    assert set(metadata.departments_needed) == {"warehouse", "lastmile"}
    assert "reverse" not in metadata.departments_needed
    assert metadata.monthly_volume == 5000


def test_metadata_never_invents_a_missing_field(informal_rfp_markdown: str):
    """La RFP informal no trae fecha límite ni presupuesto de referencia --
    deben quedar `None`, nunca un valor inventado
    ("nunca inventes... cifras que no estén en la RFP")."""

    metadata = extract_metadata(informal_rfp_markdown)

    assert metadata.deadline is None
    assert metadata.budget_range is None


def test_formal_rfp_deadline_and_budget_are_extracted(formal_rfp_markdown: str):
    metadata = extract_metadata(formal_rfp_markdown)

    assert metadata.deadline == "15 de noviembre de 2026"
    assert metadata.budget_range is not None and "EUR" in metadata.budget_range


# --- Readability: nunca inventa un score, nunca lanza -------------------------------


def test_readability_metrics_are_computed_for_real_documents(formal_rfp_markdown: str):
    from rfp_intake.pdf_conversion import compute_readability_metrics

    metrics = compute_readability_metrics(formal_rfp_markdown)
    assert metrics["status"] == "ok"
    assert metrics["flesch_reading_ease"] is not None


def test_readability_metrics_degrade_gracefully_on_short_text():
    from rfp_intake.pdf_conversion import compute_readability_metrics

    metrics = compute_readability_metrics("Texto muy corto.")
    assert metrics["status"] == "insufficient_text"
    assert metrics["flesch_reading_ease"] is None
