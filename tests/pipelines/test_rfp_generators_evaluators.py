"""Pruebas de los generadores por departamento y los evaluadores en
paralelo (`CONTEXT/CONTEXT9.md`, Hito 9 Parte 2, checklist "Pruebas").

Corren con `key_aspects` sintéticos -- sin depender de los PDF de muestra
ni de Postgres -- para poder probar tanto el camino feliz (una sección
bien escrita que debe pasar las 3 evaluaciones) como el camino de falla
(una sección deliberadamente no conforme, que el evaluador de
cumplimiento debe atrapar de verdad, no solo "no fallar nunca").
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.evaluators import (  # noqa: E402
    combine_evaluation,
    evaluate_compliance,
    evaluate_readability,
    evaluate_relevance,
)
from rfp_intake.generators import (  # noqa: E402
    generate_lastmile_section,
    generate_reverse_section,
    generate_warehouse_section,
)

# --- generadores -- nunca re-ingieren el PDF, solo key_aspects + client_country -----------


def test_warehouse_generator_mentions_only_real_key_aspects_and_correct_currency():
    key_aspects = {"monthly_volume": 3000, "client_country": "USA"}

    draft = generate_warehouse_section(key_aspects, "USA")

    assert "3000" in draft
    assert "USA" in draft
    assert "USD" in draft
    assert "EUR" not in draft


def test_warehouse_generator_never_invents_a_volume_it_was_not_given():
    draft = generate_warehouse_section({}, "Spain")

    assert "a confirmar con el cliente" in draft
    assert "EUR" in draft


def test_reverse_generator_never_promises_less_than_48h():
    draft = generate_reverse_section({"estimated_return_rate_pct": 5}, "USA")

    assert "72 horas" in draft
    assert "24 horas" not in draft


# --- evaluador de legibilidad ---------------------------------------------------------


def test_readability_evaluator_flags_insufficient_text():
    result = evaluate_readability("Texto muy corto.")

    assert result.passed is False
    assert result.score is None
    assert "insuficiente" in result.details.lower() or "corta" in result.details.lower()


def test_readability_evaluator_scores_a_real_generated_section():
    draft = generate_warehouse_section({"monthly_volume": 3000, "client_country": "USA"}, "USA")

    result = evaluate_readability(draft)

    assert result.score is not None


# --- evaluador de pertinencia ----------------------------------------------------------


def test_relevance_evaluator_passes_when_every_requested_aspect_is_mentioned():
    key_aspects = {"destination_country": "Spain", "client_sla_expectation": "90%"}
    draft = generate_lastmile_section(key_aspects, "Spain")

    result = evaluate_relevance(key_aspects, draft)

    assert result.passed is True
    assert result.missing_aspects == []


def test_relevance_evaluator_catches_a_genuinely_missing_aspect():
    key_aspects = {"destination_country": "Spain", "unexpected_requirement": "seguro de carga ampliado"}
    draft = generate_lastmile_section(key_aspects, "Spain")

    result = evaluate_relevance(key_aspects, draft)

    assert result.passed is False
    assert result.missing_aspects == ["unexpected_requirement"]


def test_relevance_evaluator_skips_boolean_flags():
    """Un flag booleano (`special_handling: True`) no tiene un texto
    literal "True" que buscar -- se omite del chequeo genérico en vez de
    producir un falso positivo."""

    key_aspects = {"destination_country": "USA", "special_handling": True}
    draft = generate_lastmile_section(key_aspects, "USA")

    result = evaluate_relevance(key_aspects, draft)

    assert result.passed is True


# --- evaluador de cumplimiento (CONTEXT9.md Sección 5) ---------------------------------


def test_compliance_evaluator_passes_a_well_formed_section():
    draft = generate_reverse_section({"estimated_return_rate_pct": 5}, "USA")

    result = evaluate_compliance("reverse", "USA", draft)

    assert result.passed is True
    assert result.violations == []


def test_compliance_evaluator_catches_wrong_currency():
    draft = "Costo cotizado en EUR. Tabla de descuentos por volumen: estándar."

    result = evaluate_compliance("warehouse", "USA", draft)

    assert result.passed is False
    assert any("currency_match" in violation for violation in result.violations)


def test_compliance_evaluator_catches_returns_under_48h():
    draft = "Promete procesamiento de devoluciones en 24 horas. Tabla de descuentos por volumen: estándar en USD."

    result = evaluate_compliance("reverse", "USA", draft)

    assert result.passed is False
    assert any("returns_48h_minimum" in violation for violation in result.violations)


def test_compliance_evaluator_catches_negotiated_carrier_rate_disclosure():
    draft = "Usamos una tarifa negociada con UPS. Tabla de descuentos por volumen: estándar en USD."

    result = evaluate_compliance("lastmile", "USA", draft)

    assert result.passed is False
    assert any("no_negotiated_carrier_rates" in violation for violation in result.violations)


def test_compliance_evaluator_does_not_require_sla_from_warehouse():
    """El SLA de entrega solo aplica a lastmile -- a warehouse no se le
    exige declararlo."""

    draft = generate_warehouse_section({"monthly_volume": 1000, "client_country": "USA"}, "USA")

    result = evaluate_compliance("warehouse", "USA", draft)

    assert "sla_stated" not in result.rule_ids
    assert result.passed is True


# --- combinación: overall_pass solo si las 3 evaluaciones pasan ------------------------


def test_overall_pass_is_false_if_any_single_evaluation_fails():
    key_aspects = {"monthly_volume": 3000, "client_country": "USA"}
    draft = generate_warehouse_section(key_aspects, "USA")

    readability = evaluate_readability(draft)
    relevance = evaluate_relevance(key_aspects, draft)
    bad_compliance = evaluate_compliance("warehouse", "USA", "Costo cotizado en EUR, sin tabla de descuentos.")

    result = combine_evaluation("warehouse", readability, relevance, bad_compliance)

    assert result.overall_pass is False


def test_overall_pass_is_true_when_all_three_evaluations_pass():
    key_aspects = {"monthly_volume": 3000, "client_country": "USA"}
    draft = generate_warehouse_section(key_aspects, "USA")

    readability = evaluate_readability(draft)
    relevance = evaluate_relevance(key_aspects, draft)
    compliance = evaluate_compliance("warehouse", "USA", draft)

    result = combine_evaluation("warehouse", readability, relevance, compliance)

    assert result.overall_pass is True
    # El modelo serializa el campo reservado `pass`, no `passed` -- CONTEXT9.md define el schema literal con `pass`.
    dumped = result.model_dump(by_alias=True)
    assert dumped["readability"]["pass"] is True
    assert "passed" not in dumped["readability"]
