"""Workers de departamento (`CONTEXT/CONTEXT9.md`, "Orquestación por
departamento"): "Cada worker recibe metadatos + extractos relevantes a su
departamento (sin inventar volúmenes/cifras que no estén en la RFP);
guarda `key_aspects` por departamento en PostgreSQL."

Cada worker es una función `(metadata, markdown_text) -> WorkerResult` --
nunca inventa un número: cuando el dato que su departamento necesita no
aparece en el documento, lo deja fuera de `key_aspects` y agrega una
pregunta abierta en `open_questions` en su lugar (`CONTEXT9.md`: "si falta
el volumen mensual, registra una pregunta abierta").
"""

from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from .classifier import RFPMetadataExtraction


class WorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: str
    key_aspects: dict[str, Any]
    open_questions: list[str] = []


# --- warehouse (Ana Whitfield) -------------------------------------------------------

_PEAK_VOLUME_RE = re.compile(
    r"picos?\s+(?:estacionales\s+)?de\s+hasta\s+([\d.,]+)\s*pedidos[^.]{0,80}", re.IGNORECASE
)


def run_warehouse_worker(metadata: RFPMetadataExtraction, markdown_text: str) -> WorkerResult:
    key_aspects: dict[str, Any] = {}
    open_questions: list[str] = []

    if metadata.monthly_volume is not None:
        key_aspects["monthly_volume"] = metadata.monthly_volume
    else:
        open_questions.append("¿Cuál es el volumen mensual estimado de pedidos?")

    peak_match = _PEAK_VOLUME_RE.search(re.sub(r"\s+", " ", markdown_text))
    if peak_match:
        key_aspects["peak_volume_context"] = peak_match.group(0).strip()

    if metadata.client_country:
        key_aspects["client_country"] = metadata.client_country
    else:
        open_questions.append("¿En qué país se ubicaría el almacenamiento?")

    return WorkerResult(department_id="warehouse", key_aspects=key_aspects, open_questions=open_questions)


# --- lastmile (Carlos Vega) ----------------------------------------------------------

_SLA_EXPECTATION_RE = re.compile(
    r"(\d+[\s-]*(?:to|-|a)?[\s-]*\d*\s*day\s+shipping|same-day|next-day|"
    r"sla\s+de\s+entrega[^.]{0,80})",
    re.IGNORECASE,
)
_HANDLING_REQUIREMENT_RE = re.compile(r"(careful handling|manejo cuidadoso|fr[aá]gil|glass bottles)", re.IGNORECASE)
_CARRIER_QUESTION_RE = re.compile(r"what carriers you work with|qu[eé] transportistas", re.IGNORECASE)


def run_lastmile_worker(metadata: RFPMetadataExtraction, markdown_text: str) -> WorkerResult:
    key_aspects: dict[str, Any] = {}
    open_questions: list[str] = []
    flattened = re.sub(r"\s+", " ", markdown_text)

    if metadata.client_country:
        key_aspects["destination_country"] = metadata.client_country
    else:
        open_questions.append("¿A qué país/región se destinan los envíos de última milla?")

    sla_match = _SLA_EXPECTATION_RE.search(flattened)
    if sla_match:
        key_aspects["client_sla_expectation"] = sla_match.group(0).strip()
    else:
        open_questions.append("¿Qué SLA de entrega espera el cliente?")

    if _HANDLING_REQUIREMENT_RE.search(flattened):
        key_aspects["special_handling"] = True

    if _CARRIER_QUESTION_RE.search(flattened):
        key_aspects["client_requests_carrier_options"] = True

    return WorkerResult(department_id="lastmile", key_aspects=key_aspects, open_questions=open_questions)


# --- reverse (Sofía Ramos) ------------------------------------------------------------

_RETURN_RATE_RE = re.compile(r"(?:tasa de devoluci[oó]n[^(]*\()?\s*(?:aproximadamente\s+)?(\d{1,3})\s*%", re.IGNORECASE)


def run_reverse_worker(metadata: RFPMetadataExtraction, markdown_text: str) -> WorkerResult:
    key_aspects: dict[str, Any] = {}
    open_questions: list[str] = []
    flattened = re.sub(r"\s+", " ", markdown_text)

    rate_match = _RETURN_RATE_RE.search(flattened)
    if rate_match:
        key_aspects["estimated_return_rate_pct"] = int(rate_match.group(1))
    else:
        open_questions.append("¿Cuál es la tasa/volumen de devoluciones esperado?")

    open_questions.append("¿Qué tiempo de procesamiento de devoluciones requiere el cliente?")

    return WorkerResult(department_id="reverse", key_aspects=key_aspects, open_questions=open_questions)


WORKER_REGISTRY: dict[str, Callable[[RFPMetadataExtraction, str], WorkerResult]] = {
    "warehouse": run_warehouse_worker,
    "lastmile": run_lastmile_worker,
    "reverse": run_reverse_worker,
}
