"""Agente clasificador (`CONTEXT/CONTEXT9.md`, "Agente clasificador"):
"Implementa un primer agente que lea el Markdown convertido y determine si
es una RFP válida. Si no lo es, detén el flujo y deja el ticket en
`descartado` (no falles en silencio)."

También extrae los metadatos de la Sección 2.3 (`client_name`,
`client_country`, `services_requested`, `monthly_volume`, `deadline`,
`budget_range`) y deriva `departments_needed` (Sección 2.1) a partir de
`services_requested` -- "no toda RFP necesita a los tres departamentos...
tu clasificador/orquestador debe decidir qué departamentos aplican según el
alcance solicitado".

## Por qué heurísticas deterministas, no un LLM real

Mismo límite documentado en toda esta sesión (`classify_intent`,
`evaluate_for_memory_proposal`, `check_instruction_override`, etc.): sin
credenciales reales de 4Geeks, la clasificación/extracción se implementa
con patrones deterministas, verificados contra el contenido REAL de los 3
PDF de muestra de `CONTEXT9.md` Sección 4 (no contra texto inventado) --
ver `tests/pipelines/test_rfp_classifier.py`. El criterio de clasificación
es específico de TrackFlow (distingue una RFP de cliente real de un pitch
de tarifas de carrier, el caso inválido exacto que pide el BRIEFING), no
un detector de "parece texto de negocios" genérico.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from .models import VALID_CLIENT_COUNTRIES, VALID_DEPARTMENT_IDS

# --- Señales de clasificación -------------------------------------------------------

# El AUTOR del documento pide los servicios de TrackFlow (es un cliente
# prospecto) -- la señal positiva de una RFP real.
_CLIENT_REQUEST_RE = re.compile(
    r"(solicitamos\s+(una\s+)?propuesta|estamos\s+evaluando\s+proveedores|"
    r"request\s+for\s+proposal|\brfp\b|"
    r"looking\s+to\s+outsource|we'?re\s+looking\s+to\s+outsource|"
    r"put\s+together\s+a\s+proposal|send\s+over\s+(some\s+)?info\s+on\s+pricing|"
    r"let\s+us\s+know\s+what\s+you\s+need\s+from\s+us|"
    r"externalizar\s+estas\s+operaciones)",
    re.IGNORECASE,
)

# El AUTOR del documento le OFRECE tarifas/servicio a TrackFlow (TrackFlow
# es el destinatario del pitch, no el proveedor evaluado) -- la señal de
# que esto NO es una RFP, el caso inválido exacto de CONTEXT9.md Sección 4.
_VENDOR_PITCH_RE = re.compile(
    r"(preferred\s+rate\s+partnership|rate\s+card|"
    r"we\s+(would\s+like\s+to\s+)?offer\s+trackflow|"
    r"(become|be)\s+one\s+of\s+your\s+preferred\s+(last-mile\s+)?partners|"
    r"competitive\s+(per-package\s+)?rates|"
    r"partnership\s+proposal)",
    re.IGNORECASE,
)


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    reason: str


def classify_rfp(markdown_text: str) -> ClassificationResult:
    """`is_valid=False` detiene el flujo (el grafo enruta a `discarded`,
    nunca a los workers) -- `reason` queda en
    `RFPTicket.discard_reason`, nunca se descarta en silencio."""

    has_client_request = bool(_CLIENT_REQUEST_RE.search(markdown_text))
    has_vendor_pitch = bool(_VENDOR_PITCH_RE.search(markdown_text))

    if has_vendor_pitch and not has_client_request:
        return ClassificationResult(
            is_valid=False,
            reason="El documento ofrece tarifas/servicios de transporte a TrackFlow (pitch de un "
            "carrier) en vez de solicitar servicios de TrackFlow -- no es una RFP de cliente.",
        )

    if has_client_request:
        return ClassificationResult(is_valid=True, reason="El documento solicita servicios de TrackFlow.")

    return ClassificationResult(
        is_valid=False,
        reason="No se encontró lenguaje de solicitud de propuesta/servicios de TrackFlow en el documento.",
    )


# --- Extracción de metadatos (CONTEXT9.md Sección 2.3) -----------------------------

_SPAIN_HINTS_RE = re.compile(r"\b(españa|espana|zaragoza|madrid|barcelona|ibérico|iberico)\b", re.IGNORECASE)
_USA_HINTS_RE = re.compile(
    r"\b(estados unidos|united states|\bUS\b|\bUSA\b|los angeles|los ángeles|california)\b", re.IGNORECASE
)

_WAREHOUSE_HINTS_RE = re.compile(r"(almacenamiento|warehousing|warehouse)", re.IGNORECASE)
_LASTMILE_HINTS_RE = re.compile(r"(última milla|ultima milla|last[\s-]?mile)", re.IGNORECASE)
_REVERSE_HINTS_RE = re.compile(r"(devoluci[oó]n|reverse logistics|returns? processing)", re.IGNORECASE)
# Negaciones -- cada una gatea SOLO su propio departamento. Mezclarlas en un
# solo patrón fue un bug real: "we handle that ourselves" (sobre
# devoluciones, en trackflow-request-2) apagaba también la detección de
# last_mile, y "propio transportista" (sobre last mile, en
# trackflow-request-1) apagaba también la de reverse -- encontrado
# corriendo el extractor contra los 3 PDF reales, no asumido de antemano.
_NO_LASTMILE_HINT_RE = re.compile(r"(no se solicita servicio de last mile|propio transportista)", re.IGNORECASE)
_NO_REVERSE_HINT_RE = re.compile(
    r"(don'?t really need help with returns|we handle that ourselves)", re.IGNORECASE
)

_MONTHLY_VOLUME_RE = re.compile(
    r"([\d.,]+)\s*(?:pedidos|orders)\s*(?:al mes|/\s*mes|a month|per month|mensuales)", re.IGNORECASE
)
_DEADLINE_RE = re.compile(
    r"(?:fecha l[ií]mite|deadline)[^\d\n]{0,40}(\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|\d{4}-\d{2}-\d{2})", re.IGNORECASE
)
_BUDGET_RANGE_RE = re.compile(
    r"(?:presupuesto|budget)[^\d\n]{0,30}((?:entre[ \t]+)?[\d.,]+[^\S\n]*(?:eur|usd|\$|€)[^.\n]{0,40})",
    re.IGNORECASE,
)
# Nombre del cliente: solo dentro de la MISMA línea (`[^\n]` en vez de
# `\s`, que también matchea saltos de línea en Markdown con párrafos
# separados por línea en blanco -- otro bug real encontrado contra el PDF 1,
# capturaba "ModaViva S.L.\n\nPaís" cruzando a la línea siguiente).
_CLIENT_NAME_RE = re.compile(
    r"(?:^Cliente:[ \t]*|We'?re[ \t]+|Somos[ \t]+)([A-Z][\wÀ-ɏ.&'’-]*(?:[ \t]+[A-Z][\wÀ-ɏ.&'’-]*){0,3})",
    re.MULTILINE,
)


class RFPMetadataExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_name: str | None = None
    client_country: str | None = None
    services_requested: list[str] = []
    monthly_volume: int | None = None
    deadline: str | None = None
    budget_range: str | None = None
    departments_needed: list[str] = []


def _extract_client_name(text: str) -> str | None:
    match = _CLIENT_NAME_RE.search(text)
    if match:
        return match.group(1).strip().rstrip(",.")
    return None


def _extract_client_country(text: str) -> str | None:
    if _SPAIN_HINTS_RE.search(text):
        return "Spain"
    if _USA_HINTS_RE.search(text):
        return "USA"
    return None


def _extract_services_and_departments(text: str) -> tuple[list[str], list[str]]:
    services: list[str] = []
    departments: list[str] = []

    if _WAREHOUSE_HINTS_RE.search(text):
        services.append("warehousing")
        departments.append("warehouse")

    # Last mile: necesita la keyword Y que no haya una negación explícita
    # de LAST MILE específicamente ("ya tenemos transportista propio").
    if _LASTMILE_HINTS_RE.search(text) and not _NO_LASTMILE_HINT_RE.search(text):
        services.append("last_mile")
        departments.append("lastmile")

    # Reverse: su propia negación específica ("ya gestionamos devoluciones
    # nosotros mismos") -- nunca la de last mile, son señales distintas.
    if _REVERSE_HINTS_RE.search(text) and not _NO_REVERSE_HINT_RE.search(text):
        services.append("reverse_logistics")
        departments.append("reverse")

    assert all(dept in VALID_DEPARTMENT_IDS for dept in departments)
    return services, departments


def _flatten_whitespace(text: str) -> str:
    """MarkItDown puede convertir un salto de línea de ajuste visual del
    PDF (una frase que se cortaba a mitad de línea en el documento
    original) en un salto de párrafo (`\\n\\n`) en el Markdown -- un
    artefacto real de conversión, no un caso de borde inventado
    (encontrado con `trackflow-request-1.pdf` real: "entre 8.000" y "EUR y
    12.000 EUR mensuales" quedaban separados por `\\n\\n` en el Markdown
    aunque son la misma frase). Los extractores de campos puntuales
    (volumen, fecha límite, presupuesto) buscan sobre esta versión
    aplanada -- nunca sobre el Markdown real que ven los agentes, donde
    los párrafos sí importan."""

    return re.sub(r"\s+", " ", text)


def _extract_monthly_volume(text: str) -> int | None:
    match = _MONTHLY_VOLUME_RE.search(_flatten_whitespace(text))
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None


def _extract_deadline(text: str) -> str | None:
    match = _DEADLINE_RE.search(_flatten_whitespace(text))
    return match.group(1).strip() if match else None


def _extract_budget_range(text: str) -> str | None:
    match = _BUDGET_RANGE_RE.search(_flatten_whitespace(text))
    return match.group(1).strip() if match else None


def extract_metadata(markdown_text: str) -> RFPMetadataExtraction:
    """Nunca inventa un valor que no esté en el texto -- cualquier campo
    sin señal clara queda `None`/lista vacía (los workers de departamento,
    `workers.py`, convierten eso en preguntas abiertas, nunca en un
    numero inventado -- `CONTEXT9.md`: "nunca inventes pallets/SKU/pedidos
    que no estén en la RFP")."""

    services, departments = _extract_services_and_departments(markdown_text)

    country = _extract_client_country(markdown_text)
    assert country is None or country in VALID_CLIENT_COUNTRIES

    return RFPMetadataExtraction(
        client_name=_extract_client_name(markdown_text),
        client_country=country,
        services_requested=services,
        monthly_volume=_extract_monthly_volume(markdown_text),
        deadline=_extract_deadline(markdown_text),
        budget_range=_extract_budget_range(markdown_text),
        departments_needed=departments,
    )
