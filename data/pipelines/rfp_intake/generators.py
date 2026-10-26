"""Agentes generadores por departamento (`CONTEXT/CONTEXT9.md`, Hito 9
Parte 2, "Generación por departamento"): "Implementa un agente generador
por departamento que reciba el resumen relevante producido en la Parte 1
(desde ese handoff)... debe producir contenido específico para la sección
de propuesta económica de su departamento."

## Qué consume cada generador -- el handoff de la Parte 1, nunca el PDF

Cada función recibe `key_aspects` (lo que el worker de ese departamento ya
extrajo en la Parte 1, `workers.py`) y `client_country` (de
`RFPMetadataRecord`, para la moneda) -- **nunca** el Markdown ni el PDF
original. Esto es lo que pide literalmente el checklist: "los generadores
no deben re-ingerir el PDF crudo como input principal".

## Por qué plantillas deterministas, no un LLM real

Mismo límite documentado en toda esta sesión: sin credenciales de 4Geeks,
"redactar" se implementa como una plantilla que interpola los
`key_aspects` reales -- nunca inventa una cifra que no vino de la Parte 1.
Cada plantilla ya respeta por diseño los lineamientos de negocio de
`CONTEXT9.md` Sección 5 (moneda correcta, tabla de descuentos, SLA
declarado donde aplica, nunca menos de 48h de procesamiento de
devoluciones, nunca una tarifa negociada con un carrier específico) --
`evaluators.py` los vuelve a chequear de forma independiente, no se confía
ciegamente en que la plantilla nunca falle.

## Ciclo generador-evaluador: cómo reacciona un generador sin LLM a `feedback`

`pipeline.py` reintenta un generador pasándole el `feedback_for_generator`
(string) del `EvaluationResult` anterior. Sin LLM, el generador no puede
"entender" prosa libre -- en cambio reconoce los mismos tokens literales
que el feedback siempre contiene (las claves de `missing_aspects` y los
`rule_id` de `violations`, ambos escritos por `evaluators.py`) y agrega
una aclaración puntual por cada uno (`_apply_feedback`). Es una reacción
real y determinista, no una regeneración idéntica disfrazada de reintento.
"""

from __future__ import annotations

from typing import Callable

CURRENCY_BY_COUNTRY = {"USA": "USD", "Spain": "EUR"}
DEFAULT_CURRENCY = "USD"


def _currency_for(client_country: str | None) -> str:
    return CURRENCY_BY_COUNTRY.get(client_country or "", DEFAULT_CURRENCY)


def _volume_discount_table(currency: str) -> str:
    return (
        "Tabla de descuentos por volumen:\n"
        f"- 0-999 unidades/mes: tarifa estándar en {currency}.\n"
        f"- 1.000-4.999 unidades/mes: 8% de descuento en {currency}.\n"
        f"- 5.000+ unidades/mes: 15% de descuento en {currency}."
    )


def _apply_feedback(lines: list[str], key_aspects: dict, currency: str, feedback: str | None) -> list[str]:
    """Ver docstring del módulo ("Ciclo generador-evaluador") -- reconoce
    los tokens literales que `evaluators.py` siempre escribe en el
    feedback (claves de `missing_aspects`, `rule_id` de `violations`) y
    agrega una aclaración puntual por cada uno."""

    if not feedback:
        return lines

    lines = list(lines)
    for key, value in key_aspects.items():
        if value in (None, "", False):
            continue
        if key in feedback:
            lines.append(f"Aclaración adicional solicitada ({key}): {value}.")

    if "currency_match" in feedback:
        lines.append(f"Aclaración de moneda: todos los montos de esta sección están expresados en {currency}.")
    if "volume_discount_table_present" in feedback:
        lines.append(_volume_discount_table(currency))
    if "no_negotiated_carrier_rates" in feedback:
        lines.append(
            "Aclaración de cumplimiento: no se revela ninguna tarifa negociada con un transportista "
            "específico, solo el costo final ofrecido al cliente."
        )
    if "sla_stated" in feedback:
        lines.append("Aclaración de SLA: SLA de entrega a tiempo comprometido por TrackFlow: 95%.")
    if "returns_48h_minimum" in feedback:
        lines.append(
            "Aclaración de cumplimiento: el procesamiento de devoluciones se compromete en 72 horas "
            "desde la recepción en almacén, nunca menos de 48 horas."
        )
    return lines


def generate_warehouse_section(key_aspects: dict, client_country: str | None, feedback: str | None = None) -> str:
    currency = _currency_for(client_country)
    monthly_volume = key_aspects.get("monthly_volume")
    volume_line = (
        f"Volumen mensual estimado: {monthly_volume} pedidos."
        if monthly_volume is not None
        else "Volumen mensual estimado: a confirmar con el cliente (no especificado en la RFP)."
    )
    peak_line = key_aspects.get("peak_volume_context")
    client_country = key_aspects.get("client_country")

    lines = [
        "Sección de Warehouse Operations — Propuesta Económica",
        "El equipo de Warehouse Operations de TrackFlow gestionaría el almacenamiento del "
        "inventario del cliente, con control de stock en tiempo real y procesos de recepción "
        "y despacho pensados para minimizar el tiempo de onboarding de un cliente nuevo. "
        "El objetivo es que la mercancía quede disponible para despacho lo antes posible, "
        "con visibilidad permanente sobre el nivel de stock en cada almacén.",
        f"Ubicación de la operación: {client_country or 'a confirmar con el cliente'}.",
        volume_line,
    ]
    if peak_line:
        lines.append(f"Contexto de picos estacionales: {peak_line}.")
    lines += [
        f"Costo por pallet/SKU y tiempo de onboarding: cotizados en {currency}.",
        _volume_discount_table(currency),
    ]
    lines = _apply_feedback(lines, key_aspects, currency, feedback)
    return "\n".join(lines)


def generate_lastmile_section(key_aspects: dict, client_country: str | None, feedback: str | None = None) -> str:
    currency = _currency_for(client_country)
    sla_hint = key_aspects.get("client_sla_expectation")

    lines = [
        "Sección de Last Mile and Carrier Management — Propuesta Económica",
        "El equipo de Last Mile and Carrier Management de TrackFlow coordinaría la entrega final "
        "al destinatario, seleccionando transportistas según la zona de destino y el volumen "
        "comprometido, con seguimiento del envío disponible para el cliente en todo momento.",
        f"Destino: {key_aspects.get('destination_country', 'a confirmar con el cliente')}.",
        "SLA de entrega a tiempo comprometido por TrackFlow: 95%.",
    ]
    if sla_hint:
        lines.append(f"Referencia de expectativa del cliente: {sla_hint}.")
    if key_aspects.get("special_handling"):
        lines.append("Manejo especial requerido para mercancía frágil, incluido en el costo cotizado.")
    lines += [
        f"Costo por envío: cotizado en {currency}, costo final ofrecido al cliente "
        "(no se revelan tarifas negociadas con transportistas específicos).",
        _volume_discount_table(currency),
    ]
    lines = _apply_feedback(lines, key_aspects, currency, feedback)
    return "\n".join(lines)


def generate_reverse_section(key_aspects: dict, client_country: str | None, feedback: str | None = None) -> str:
    currency = _currency_for(client_country)
    return_rate = key_aspects.get("estimated_return_rate_pct")
    rate_line = (
        f"Tasa de devolución estimada: {return_rate}%."
        if return_rate is not None
        else "Tasa de devolución estimada: a confirmar con el cliente (no especificada en la RFP)."
    )

    lines = [
        "Sección de Reverse Logistics — Propuesta Económica",
        "El equipo de Reverse Logistics de TrackFlow gestionaría la recepción, inspección y "
        "reingreso a inventario de los productos devueltos, con un proceso diseñado para que el "
        "cliente recupere stock vendible lo antes posible sin comprometer el control de calidad.",
        rate_line,
        # Nunca < 48h (CONTEXT9.md Sección 5) -- 72h por diseño, con margen.
        "Tiempo de procesamiento de devoluciones comprometido: 72 horas desde la recepción en almacén.",
        f"Costo de procesamiento de devoluciones: cotizado en {currency}.",
        _volume_discount_table(currency),
    ]
    lines = _apply_feedback(lines, key_aspects, currency, feedback)
    return "\n".join(lines)


GENERATOR_REGISTRY: dict[str, Callable[[dict, str | None], str]] = {
    "warehouse": generate_warehouse_section,
    "lastmile": generate_lastmile_section,
    "reverse": generate_reverse_section,
}
