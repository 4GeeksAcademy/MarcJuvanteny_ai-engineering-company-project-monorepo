"""Clasificación de la resolución de una propuesta de memoria pendiente
(`CONTEXT/CONTEXT8.md`, "Confirmación del Usuario y Registro Auditable").

El checklist exige explícitamente "una clasificación de intención explícita
(etiqueta estructurada / clasificador), no un simple `'sí' in mensaje`" --
un `in` ingenuo clasificaría mal frases como "no sé si eso es así" (contiene
"sí" como substring sin ser una aprobación) o "sí, pero mejor que diga X"
(aprobación Y edición a la vez). `classify_memory_decision()` usa patrones
de palabra completa (`\\b`) sobre el mensaje COMPLETO, y por diseño
prioriza "edited" sobre "approved" cuando el mensaje trae ambas señales
(una aprobación con una corrección sigue siendo una edición, no una
aprobación lisa).

Cualquier mensaje que no dispare ninguno de los tres patrones (el usuario
cambió de tema, hizo otra pregunta, fue ambiguo) se clasifica como
`"rejected"` -- la propuesta se descarta por defecto, nunca se asume
aprobación por silencio o ambigüedad (regla explícita del checklist).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["approved", "rejected", "edited"]

_APPROVE_RE = re.compile(
    r"^\s*(s[ií]|sip|dale|correcto|exacto|confirmo|aprobado|as[ií] es|perfecto)\b", re.IGNORECASE
)
_REJECT_RE = re.compile(
    r"^\s*(no|descartalo|descártalo|ignora eso|olv[ií]dalo|mejor no|negativo)\b", re.IGNORECASE
)
_EDIT_TRIGGER_RE = re.compile(
    r"\b(pero|en realidad|mejor que diga|c[aá]mbialo a|en vez de eso|corrig[ei]|deber[ií]a decir)\b", re.IGNORECASE
)


class MemoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    edited_fact: str | None = None


def classify_memory_decision(user_message: str) -> MemoryDecision:
    stripped = user_message.strip()
    if not stripped:
        return MemoryDecision(outcome="rejected")

    # Una edición (con o sin un si/no explicito al frente) prevalece sobre
    # una aprobacion/rechazo liso -- el usuario no quiere exactamente lo
    # propuesto, quiere una version corregida.
    if _EDIT_TRIGGER_RE.search(stripped):
        return MemoryDecision(outcome="edited", edited_fact=stripped)

    if _APPROVE_RE.match(stripped):
        return MemoryDecision(outcome="approved")

    if _REJECT_RE.match(stripped):
        return MemoryDecision(outcome="rejected")

    # Cambio de tema / mensaje ambiguo -> descartado por defecto.
    return MemoryDecision(outcome="rejected")
