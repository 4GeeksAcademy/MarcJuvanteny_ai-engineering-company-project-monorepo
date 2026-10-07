"""Auto-evaluación y propuesta de memoria (`CONTEXT/CONTEXT8.md`, Hito 8
Parte 1, "Auto-evaluación y Propuesta de Memoria").

## Una sola llamada, no una segunda arquitectura

El checklist pide explícitamente que esto sea "el mismo agente con un campo
adicional en su salida" -- una llamada de generación con salida
estructurada: la respuesta visible, más un campo `propuesta_memoria`
opcional. Sin credenciales reales de 4Geeks en este repo (mismo límite que
`classify_intent()`/`extract_incident_query()` en `agent_graph.py`), esto se
implementa con una heurística determinista y documentada --
`evaluate_for_memory_proposal()` -- en el punto exacto donde una llamada
real de generación con `response_format`/function-calling iría en
producción: dentro del mismo nodo `propose_memory` de `agent_graph.py`,
nunca como una segunda llamada al modelo ni un agente separado.

## Qué es memorizable -- exactamente lo que dice CONTEXT-company.md, no una
## versión genérica

`CONTEXT8.md` especifica 3 categorías permitidas y 3 terminantemente
prohibidas. Esta heurística las implementa como dos pasos: primero
reconoce un patrón candidato (regla de carrier corregida, contexto de
incidente recurrente, preferencia de cliente B2B); luego, ANTES de
proponerlo, lo filtra contra los patrones prohibidos (dirección/ubicación
de cliente final, incidente puntual sin patrón repetible, contrato
comercial en negociación) -- un candidato que dispara el patrón permitido
pero también el prohibido NUNCA se propone. Ver `tests/pipelines/test_agent_memory.py`
para los 3 ejemplos positivos y los 3+3 negativos (los del checklist
genérico + los específicos de `CONTEXT8.md`) que esta función debe
clasificar correctamente.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

VALID_COUNTRIES = ("USA", "Spain")
# País real de cada carrier (`docs/company-knowledge-base/trackflow-carrier-coverage.es.md`)
# -- fuente de verdad confiable, a diferencia de adivinar el país por
# nombres de ciudad en el texto libre (ver bug real documentado en
# `extract_country()`). `None` = el carrier opera en ambos países bajo el
# mismo nombre (solo "DHL Express" sin calificar "USA"/"España"), así que
# ahí sí hace falta el texto.
_CARRIER_COUNTRY: dict[str, str | None] = {
    "UPS Ground": "USA",
    "FedEx Ground": "USA",
    "OnTrac": "USA",
    "DHL Express USA": "USA",
    "DHL Express España": "Spain",
    "DHL Express": None,
    "MRW España": "Spain",
    "MRW": "Spain",
    "SEUR": "Spain",
    "Nacex": "Spain",
}
_CARRIER_NAMES = tuple(_CARRIER_COUNTRY.keys())

# --- Patrones PROHIBIDOS (CONTEXT8.md, "Qué NUNCA debe entrar en la memoria") -------

_FORBIDDEN_LOCATION_RE = re.compile(
    r"\b(calle|avenida|av\.|c\/|direcci[oó]n (del|de la) client[ea]|domicilio del client[ea])\b", re.IGNORECASE
)
_FORBIDDEN_WAREHOUSE_ROUTE_RE = re.compile(r"\bruta (interna|del almac[eé]n)\b", re.IGNORECASE)
_FORBIDDEN_CONTRACT_RE = re.compile(
    r"\b(contrato comercial|negociaci[oó]n (del|de) contrato|en negociaci[oó]n)\b", re.IGNORECASE
)
_SINGLE_TRACKING_RE = re.compile(r"\btracking\s+[a-z0-9]{4,}\b", re.IGNORECASE)

# --- Patrones de interacciones que NUNCA proponen (checklist genérico) -------------

_CLOSING_PHRASES_RE = re.compile(
    r"^\s*(perfecto,?\s*)?(ya\s+)?(qued[oó]\s+resuelto|gracias|listo|de nada|perfecto)\.?\s*$", re.IGNORECASE
)
_ONE_OFF_TASK_RE = re.compile(r"\b(tradu[cz]e|traducci[oó]n|resume|resumen|formatea)\b", re.IGNORECASE)

# --- Patrones candidatos (categorías permitidas) -----------------------------------

_CARRIER_RULE_RE = re.compile(
    r"\b(ya no (cubre|opera)|dej[oó] de (cubrir|operar)|cambi[oó] (su )?cobertura|"
    r"desde el mes pasado|hay que usar)\b",
    re.IGNORECASE,
)
_RECURRING_INCIDENT_RE = re.compile(
    r"\b(ya van \d+ tickets|ya van varios tickets|no (es|son) (un )?problema nuestro|"
    r"es por la huelga|esta semana son por)\b",
    re.IGNORECASE,
)
_CLIENT_PREFERENCE_RE = re.compile(
    r"\b(siempre quiere|prefiere que|antes que el|primero,? antes de)\b", re.IGNORECASE
)
_CLIENT_DESCRIPTOR_RE = re.compile(r"\bcliente\s+(?:de\s+)?([a-záéíóúñü]+)\b", re.IGNORECASE)


class MemoryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    category: str
    fact: str
    reason: str


_SPAIN_LOCATION_HINTS = ("zaragoza", "aragón", "aragon", "españa", "espana", "barcelona", "madrid", "baleares")


def extract_country(text: str, *, carrier: str | None = None) -> str:
    """Si `carrier` es uno de los 8 carriers conocidos y opera en un solo
    país, el país sale del carrier mismo -- confiable, nunca ambiguo. Solo
    cae al texto libre (nombres de ciudad/región) cuando no hay carrier o
    el carrier opera en ambos países sin calificar (`"DHL Express"` a
    secas). Bug real encontrado documentando la "Evidencia" de esta
    entrega: una pregunta sobre "Nacex" y "Aragón" (sin mencionar
    "Zaragoza") se clasificaba como `"USA"` porque el heurístico de texto
    no reconocía "Aragón" -- Nacex es un carrier exclusivo de España, el
    carrier mismo ya lo dice sin ambigüedad."""

    if carrier is not None:
        known_country = _CARRIER_COUNTRY.get(carrier)
        if known_country is not None:
            return known_country

    lowered = text.lower()
    if any(hint in lowered for hint in _SPAIN_LOCATION_HINTS):
        return "Spain"
    return "USA"


def extract_carrier(text: str) -> str | None:
    for name in _CARRIER_NAMES:
        if name.lower() in text.lower():
            return name
    return None


def _is_forbidden(text: str) -> bool:
    """`CONTEXT8.md`, "Qué NUNCA debe entrar en la memoria" -- chequeado
    SIEMPRE, incluso si el texto también dispara un patrón permitido."""

    if _FORBIDDEN_LOCATION_RE.search(text) or _FORBIDDEN_WAREHOUSE_ROUTE_RE.search(text):
        return True
    if _FORBIDDEN_CONTRACT_RE.search(text):
        return True
    # Un tracking puntual sin lenguaje de recurrencia ("ya van N tickets") es
    # una incidencia aislada, no un patrón repetible.
    if _SINGLE_TRACKING_RE.search(text) and not _RECURRING_INCIDENT_RE.search(text):
        return True
    return False


def evaluate_for_memory_proposal(question: str, answer: str) -> MemoryProposal | None:
    """Heurística determinista (ver docstring del módulo). Evalúa SOLO el
    mensaje del usuario (`question`), nunca `answer` -- `answer` se recibe
    en la firma para que el punto de inyección quede listo para una
    implementación real por LLM que sí quiera considerar la respuesta
    completa, pero usarla acá tiene un bug real y comprobado: una vez que un
    hecho aprobado se inyecta como contexto (`retrieve_memory`) y
    `generate_answer()` lo repite en una respuesta futura, evaluar
    `question + answer` combinados vuelve a detectar ese mismo texto y
    re-propone el hecho que el usuario YA aprobó, en un loop. Confirmado
    corriendo el flujo completo de punta a punta (propuesta -> aprobación ->
    pregunta nueva que reutiliza la memoria) antes de fijar este
    comportamiento -- ver Pasos/."""

    stripped_question = question.strip()

    if _CLOSING_PHRASES_RE.match(stripped_question) or _ONE_OFF_TASK_RE.search(stripped_question):
        return None

    if _is_forbidden(stripped_question):
        return None

    carrier = extract_carrier(stripped_question)
    if carrier and _CARRIER_RULE_RE.search(stripped_question):
        country = extract_country(stripped_question, carrier=carrier)
        return MemoryProposal(
            key=f"{carrier}:{country}",
            category="carrier_rule",
            fact=question.strip(),
            reason=f"Corrección de regla de asignación para {carrier} ({country}).",
        )

    if _RECURRING_INCIDENT_RE.search(stripped_question):
        country = extract_country(stripped_question)
        return MemoryProposal(
            key=f"incident_context:{country}",
            category="incident_context",
            fact=question.strip(),
            reason="Contexto recurrente de incidentes, útil para no re-escalar la misma alerta.",
        )

    if _CLIENT_PREFERENCE_RE.search(stripped_question):
        descriptor_match = _CLIENT_DESCRIPTOR_RE.search(stripped_question)
        descriptor = descriptor_match.group(1).lower() if descriptor_match else "unspecified"
        return MemoryProposal(
            key=f"client_preference:{descriptor}",
            category="client_preference",
            fact=question.strip(),
            reason="Preferencia recurrente de un cliente B2B sobre su reporte.",
        )

    return None
