"""Agentes evaluadores (`CONTEXT/CONTEXT9.md`, Hito 9 Parte 2, "Evaluación
en paralelo"): legibilidad, pertinencia, y cumplimiento de los lineamientos
de negocio -- cada uno independiente, persistidos como un `EvaluationResult`
estructurado.

Los 3 evaluadores corren en paralelo de verdad vía LangGraph
(`evaluation_graph.py`), no solo llamados en secuencia uno tras otro -- ver
ese módulo para el fan-out real, con el mismo patrón de "una clave de
estado por rama" que ya se verificó necesario en Parte 1 (`graph.py`).

## Por qué heurísticas deterministas para pertinencia/cumplimiento

Mismo límite de toda la sesión: sin credenciales de 4Geeks, "pertinencia"
se implementa chequeando que cada valor real de `key_aspects` (lo que la
Parte 1 ya extrajo de la RFP) aparezca mencionado en el borrador -- no una
evaluación semántica por LLM. "Cumplimiento" chequea los 5 lineamientos
exactos de `CONTEXT9.md` Sección 5, no una lista genérica de reglas.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from .generators import CURRENCY_BY_COUNTRY, DEFAULT_CURRENCY
from .pdf_conversion import compute_readability_metrics

# Flesch Reading Ease está calibrado para inglés -- texto en español,
# incluso bien escrito, puntúa sistemáticamente más bajo ("very_confusing"
# en vez de "difficult"/"standard"). Ya documentado en
# Pasos/rag-knowledge-base-fase1.md para el mismo motivo. El umbral se fija
# bajo (10, no 30+) a propósito para no reprobar prosa de negocio en
# español razonable solo por el sesgo de calibración del inglés de la
# fórmula -- confirmado corriendo los 3 templates reales de
# `generators.py` (ver Pasos/), que puntúan 22-32 en español.
MIN_FLESCH_READING_EASE = 10.0

VALID_RULE_IDS = (
    "currency_match",
    "sla_stated",
    "returns_48h_minimum",
    "volume_discount_table_present",
    "no_negotiated_carrier_rates",
)


class ReadabilityEvaluation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    passed: bool = Field(alias="pass")
    score: float | None
    details: str


class RelevanceEvaluation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    passed: bool = Field(alias="pass")
    missing_aspects: list[str]


class ComplianceEvaluation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    passed: bool = Field(alias="pass")
    rule_ids: list[str]
    violations: list[str]


class EvaluationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    department_id: str
    readability: ReadabilityEvaluation
    relevance: RelevanceEvaluation
    compliance: ComplianceEvaluation
    overall_pass: bool
    # Checklist de "Ciclo generador-evaluador": "el flujo debe devolverla al
    # agente generador correspondiente junto con el feedback_for_generator
    # del EvaluationResult" -- reutiliza los mismos tokens (rule_id,
    # missing_aspects) que `generators.py::_apply_feedback` reconoce, no una
    # frase genérica.
    feedback_for_generator: str


# --- Legibilidad ----------------------------------------------------------------------


def evaluate_readability(draft_content: str) -> ReadabilityEvaluation:
    metrics = compute_readability_metrics(draft_content)

    if metrics["status"] == "insufficient_text":
        return ReadabilityEvaluation(
            **{"pass": False},
            score=None,
            details="Sección demasiado corta para medir legibilidad (<100 palabras).",
        )

    score = metrics["flesch_reading_ease"]
    passed = score >= MIN_FLESCH_READING_EASE
    return ReadabilityEvaluation(
        **{"pass": passed},
        score=score,
        details=f"Flesch Reading Ease: {score:.1f} ({metrics['flesch_reading_ease_label']}).",
    )


# --- Pertinencia ------------------------------------------------------------------------


def evaluate_relevance(key_aspects: dict, draft_content: str) -> RelevanceEvaluation:
    """Cada valor real de `key_aspects` (lo que la RFP realmente pedía,
    según la Parte 1) debe aparecer mencionado en el borrador -- si algo
    que el cliente pidió no se menciona, es una sección que no responde la
    RFP, sin importar qué tan bien redactada esté."""

    lowered_draft = draft_content.lower()
    missing: list[str] = []

    for key, value in key_aspects.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            # Un flag booleano no tiene un texto literal que buscar (no se busca la palabra "True").
            continue
        value_text = str(value).lower()
        if value_text not in lowered_draft:
            missing.append(key)

    return RelevanceEvaluation(**{"pass": not missing}, missing_aspects=missing)


# --- Cumplimiento (CONTEXT9.md Sección 5) ------------------------------------------------

_SLA_STATED_RE = re.compile(r"sla de entrega[^.]*\d{1,3}\s*%", re.IGNORECASE)
_RETURNS_HOURS_RE = re.compile(r"devoluciones?[^.]{0,60}?(\d{1,3})\s*horas", re.IGNORECASE)
_VOLUME_DISCOUNT_RE = re.compile(r"tabla de descuentos por volumen", re.IGNORECASE)
_NEGOTIATED_CARRIER_RATE_RE = re.compile(
    r"tarifa\s+negociada\s+con\s+(ups|fedex|dhl|mrw|seur|onTrac|nacex)", re.IGNORECASE
)

# Qué reglas aplican a qué departamento -- CONTEXT9.md Sección 5 no las
# aclara por departamento, pero solo tiene sentido pedirle "SLA de
# entrega" a lastmile y "procesamiento de devoluciones" a reverse; las
# demás (moneda, tabla de descuentos, nunca revelar tarifas negociadas)
# aplican a cualquier sección, porque cualquiera podría mencionar un
# costo.
_DEPARTMENT_SPECIFIC_RULES = {
    "lastmile": ("sla_stated",),
    "reverse": ("returns_48h_minimum",),
}
_UNIVERSAL_RULES = ("currency_match", "volume_discount_table_present", "no_negotiated_carrier_rates")


def evaluate_compliance(department_id: str, client_country: str | None, draft_content: str) -> ComplianceEvaluation:
    applicable_rules = list(_UNIVERSAL_RULES) + list(_DEPARTMENT_SPECIFIC_RULES.get(department_id, ()))
    violations: list[str] = []

    expected_currency = CURRENCY_BY_COUNTRY.get(client_country or "", DEFAULT_CURRENCY)
    other_currencies = [c for c in set(CURRENCY_BY_COUNTRY.values()) if c != expected_currency]
    if expected_currency not in draft_content:
        violations.append(f"currency_match: no se menciona la moneda esperada ({expected_currency}).")
    elif any(currency in draft_content for currency in other_currencies):
        violations.append(f"currency_match: se menciona una moneda distinta a la esperada ({expected_currency}).")

    if "volume_discount_table_present" in applicable_rules and not _VOLUME_DISCOUNT_RE.search(draft_content):
        violations.append("volume_discount_table_present: no se encontró una tabla de descuentos por volumen.")

    if _NEGOTIATED_CARRIER_RATE_RE.search(draft_content):
        violations.append("no_negotiated_carrier_rates: la sección revela una tarifa negociada con un carrier específico.")

    if "sla_stated" in applicable_rules and not _SLA_STATED_RE.search(draft_content):
        violations.append("sla_stated: no se declara el SLA de entrega a tiempo (%).")

    if "returns_48h_minimum" in applicable_rules:
        for match in _RETURNS_HOURS_RE.finditer(draft_content):
            hours = int(match.group(1))
            if hours < 48:
                violations.append(
                    f"returns_48h_minimum: promete procesamiento de devoluciones en {hours}h (< 48h mínimo)."
                )

    return ComplianceEvaluation(**{"pass": not violations}, rule_ids=applicable_rules, violations=violations)


# --- Combinación -------------------------------------------------------------------------


def build_feedback_for_generator(
    readability: ReadabilityEvaluation,
    relevance: RelevanceEvaluation,
    compliance: ComplianceEvaluation,
) -> str:
    """Un reintento sin feedback concreto sería un reintento ciego --
    cada frase nombra exactamente lo que falló, con los mismos tokens
    (`missing_aspects`, `rule_id`) que `generators.py::_apply_feedback`
    busca para reaccionar de forma determinista en la siguiente
    regeneración."""

    parts: list[str] = []
    if not readability.passed:
        parts.append(f"Legibilidad: {readability.details} Simplifica las oraciones y agrega contexto explicativo.")
    if not relevance.passed:
        parts.append(
            "Pertinencia: faltan mencionar estos aspectos solicitados por el cliente: "
            + ", ".join(relevance.missing_aspects)
            + "."
        )
    if not compliance.passed:
        parts.append("Cumplimiento: " + " ".join(compliance.violations))
    return " ".join(parts) if parts else "Sección aprobada, no se requieren cambios."


def combine_evaluation(
    department_id: str,
    readability: ReadabilityEvaluation,
    relevance: RelevanceEvaluation,
    compliance: ComplianceEvaluation,
) -> EvaluationResult:
    return EvaluationResult(
        department_id=department_id,
        readability=readability,
        relevance=relevance,
        compliance=compliance,
        overall_pass=readability.passed and relevance.passed and compliance.passed,
        feedback_for_generator=build_feedback_for_generator(readability, relevance, compliance),
    )
