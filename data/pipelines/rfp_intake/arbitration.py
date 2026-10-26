"""Nodo de arbitraje (`CONTEXT/CONTEXT9.md` Sección 7, "Parte 3 — Triggers
de conflicto y árbitro fijo"): "El arbitraje debe ser un nodo dedicado del
grafo disparado por contradicciones detectables en estado estructurado,
no por agentes negociando entre ellos... Los agentes pueden señalar un
conflicto; no deben resolverlo por consenso libre."

Los 3 triggers, árbitros y reglas de resolución son EXACTOS de la tabla
de la Sección 7 -- nunca un árbitro LLM "libre", siempre el humano
nombrado fijo que el BRIEFING asigna a cada trigger.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from .generators import CURRENCY_BY_COUNTRY, DEFAULT_CURRENCY

# `warehouse` no tiene un campo explícito de "capacidad máxima" en
# key_aspects (la RFP solo da el volumen que el CLIENTE pide, nunca la
# capacidad propia de TrackFlow) -- `CONTEXT9.md` no da un número exacto
# para `volume-vs-capacity`, así que se documenta acá como una constante
# operativa de TrackFlow (no inventada por RFP, es un límite de la
# EMPRESA): throughput máximo de onboarding que Warehouse Operations
# puede comprometer de forma realista en una propuesta nueva.
WAREHOUSE_MAX_MONTHLY_CAPACITY = 4000

MIGUEL_TORRES = "Miguel Torres (Director Comercial)"
SOFIA_RAMOS = "Sofía Ramos"

_RETURNS_HOURS_RE = re.compile(r"devoluciones?[^.]{0,60}?(\d{1,3})\s*horas", re.IGNORECASE)


class ArbitrationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_id: str
    arbiter: str
    rule_applied: str
    affected_departments: list[str]
    resolved: bool
    timestamp: str


def _currency_in_text(text: str) -> str | None:
    for currency in set(CURRENCY_BY_COUNTRY.values()) | {DEFAULT_CURRENCY}:
        if currency in text:
            return currency
    return None


def check_volume_vs_capacity(sections: dict[str, dict[str, Any]]) -> ArbitrationDecision | None:
    """`volume-vs-capacity`: la capacidad comprometida de `warehouse` no
    soporta el volumen mensual asumido por `lastmile`. Árbitro: Miguel
    Torres. Regla: limitar el volumen de la propuesta a la capacidad de
    warehouse; `lastmile` debe revisar volumen/costo a la baja."""

    warehouse = sections.get("warehouse")
    lastmile = sections.get("lastmile")
    if warehouse is None or lastmile is None:
        return None

    monthly_volume = (warehouse.get("key_aspects") or {}).get("monthly_volume")
    if monthly_volume is None or monthly_volume <= WAREHOUSE_MAX_MONTHLY_CAPACITY:
        return None

    return ArbitrationDecision(
        trigger_id="volume-vs-capacity",
        arbiter=MIGUEL_TORRES,
        rule_applied=(
            f"Volumen mensual asumido ({monthly_volume}) excede la capacidad de warehouse "
            f"({WAREHOUSE_MAX_MONTHLY_CAPACITY}) -- se limita la propuesta a la capacidad disponible; "
            "lastmile debe revisar volumen/costo a la baja."
        ),
        affected_departments=["warehouse", "lastmile"],
        resolved=False,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def check_returns_sla_breach(sections: dict[str, dict[str, Any]]) -> ArbitrationDecision | None:
    """`returns-sla-breach`: alguna sección promete devoluciones en menos
    de 48h (viola §5). Árbitro: Sofía Ramos rechaza su propia sección
    (`reverse`); si OTRO departamento aún embebe esa promesa, Miguel
    Torres. Regla: forzar `request_changes` en toda sección ofensora; sin
    documento final hasta cumplir."""

    offending_departments = []
    for department_id, section in sections.items():
        draft = section.get("draft_content") or ""
        for match in _RETURNS_HOURS_RE.finditer(draft):
            if int(match.group(1)) < 48:
                offending_departments.append(department_id)
                break

    if not offending_departments:
        return None

    arbiter = SOFIA_RAMOS if offending_departments == ["reverse"] else MIGUEL_TORRES
    return ArbitrationDecision(
        trigger_id="returns-sla-breach",
        arbiter=arbiter,
        rule_applied=(
            "Al menos una sección promete procesamiento de devoluciones en menos de 48h -- "
            "se fuerza request_changes en toda sección ofensora; sin documento final hasta cumplir."
        ),
        affected_departments=offending_departments,
        resolved=False,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def check_currency_mismatch(
    sections: dict[str, dict[str, Any]], client_country: str | None
) -> ArbitrationDecision | None:
    """`currency-mismatch`: dos secciones activas cotizan monedas
    distintas, o la moneda != mapeo de `client_country`. Árbitro: Miguel
    Torres. Regla: reescribir las secciones ofensoras a la moneda del
    país; rechazar si no se resuelve tras el límite de iteraciones (la
    aplicación de ese límite vive en `approval_graph.py`, no acá -- este
    chequeo solo SEÑALA el conflicto)."""

    expected_currency = CURRENCY_BY_COUNTRY.get(client_country or "", DEFAULT_CURRENCY)
    offending_departments = []
    for department_id, section in sections.items():
        draft = section.get("draft_content") or ""
        currency_in_draft = _currency_in_text(draft)
        if currency_in_draft is not None and currency_in_draft != expected_currency:
            offending_departments.append(department_id)

    if not offending_departments:
        return None

    return ArbitrationDecision(
        trigger_id="currency-mismatch",
        arbiter=MIGUEL_TORRES,
        rule_applied=(
            f"Sección(es) cotizan en una moneda distinta a la esperada ({expected_currency} para "
            f"client_country={client_country!r}) -- se reescriben a la moneda correcta."
        ),
        affected_departments=offending_departments,
        resolved=False,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def run_arbitration(sections: dict[str, dict[str, Any]], client_country: str | None) -> list[ArbitrationDecision]:
    """Corre los 3 triggers en el orden de la tabla de la Sección 7 --
    nunca un LLM decidiendo cuál aplica primero."""

    decisions = []
    for check in (
        lambda: check_volume_vs_capacity(sections),
        lambda: check_returns_sla_breach(sections),
        lambda: check_currency_mismatch(sections, client_country),
    ):
        decision = check()
        if decision is not None:
            decisions.append(decision)
    return decisions
