"""Conversión PDF -> Markdown + métricas de legibilidad (`CONTEXT/CONTEXT9.md`,
"Ingesta y conversión del documento"): "Convierte cada RFP de PDF a
Markdown antes de que cualquier agente la lea (obligatorio: MarkItDown o
equivalente documentado)".

Usa MarkItDown real (paquete `markitdown` de PyPI, no una reimplementación
propia) -- ningún agente de este pipeline lee el PDF crudo, todos leen el
Markdown que produce este módulo.

## Métricas de legibilidad

`py-readability-metrics` (sugerido por `CONTEXT9.md`) real -- Flesch
Reading Ease + Flesch-Kincaid Grade Level, usados como proxy barato del
costo de procesamiento (texto más complejo/denso → más tokens/iteraciones
probables en los agentes de las Partes 2-3). Requiere ≥100 palabras
(`readability.exceptions.ReadabilityException` si el documento es más
corto) -- un RFP real de varias páginas lo cumple holgadamente; un
documento demasiado corto para medir se marca explícitamente
(`"insufficient_text"`), nunca se inventa un score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from markitdown import MarkItDown


def convert_pdf_to_markdown(pdf_path: str | Path) -> str:
    """Única función que lee el PDF crudo en todo el pipeline -- todo lo
    demás (clasificador, workers, synthesizer) opera sobre el string que
    devuelve esta función, nunca sobre el PDF."""

    converter = MarkItDown()
    result = converter.convert_local(str(pdf_path))
    return result.markdown


def compute_readability_metrics(markdown_text: str) -> dict[str, Any]:
    """Nunca lanza -- un documento demasiado corto para medir (<100
    palabras, ver docstring del módulo) devuelve un dict explícito en vez
    de hacer fallar todo el pipeline por una métrica secundaria."""

    from readability import Readability
    from readability.exceptions import ReadabilityException

    # La excepción de "muy corto para medir" no se lanza en el constructor
    # -- recien aparece al pedir un score puntual (`.flesch()`), algo que
    # solo se descubrió corriendo un texto corto real contra esta función
    # (un test que esperaba que el constructor solo fallara, no pasaba).
    try:
        readability = Readability(markdown_text)
        flesch = readability.flesch()
        flesch_kincaid = readability.flesch_kincaid()
    except ReadabilityException:
        return {"status": "insufficient_text", "flesch_reading_ease": None, "flesch_kincaid_grade": None}

    return {
        "status": "ok",
        "flesch_reading_ease": flesch.score,
        "flesch_reading_ease_label": flesch.ease,
        "flesch_kincaid_grade": flesch_kincaid.score,
    }
