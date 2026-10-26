"""Pruebas del ciclo generador-evaluador (`CONTEXT/CONTEXT9.md`, Hito 9
Parte 2, checklist "Ciclo generador-evaluador"): reintento con
`feedback_for_generator`, límite de iteraciones, y escalamiento a
`needs_human_review` sin descartar la sección.

`_generate_and_evaluate_with_retries` recibe `generator_fn`/`evaluate_fn`
inyectables -- mismo patrón de testabilidad que `test_rfp_workers.py` y
`test_rfp_generation_evaluation_graphs.py` -- para forzar fallos
deterministas sin depender de Postgres ni de que el generador real falle.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.evaluators import combine_evaluation, evaluate_compliance  # noqa: E402
from rfp_intake.generators import generate_reverse_section  # noqa: E402
from rfp_intake.pipeline import _generate_and_evaluate_with_retries  # noqa: E402


def _passing_evaluation(department_id: str) -> dict:
    from rfp_intake.evaluators import ComplianceEvaluation, ReadabilityEvaluation, RelevanceEvaluation

    result = combine_evaluation(
        department_id,
        ReadabilityEvaluation(**{"pass": True}, score=50.0, details="ok"),
        RelevanceEvaluation(**{"pass": True}, missing_aspects=[]),
        ComplianceEvaluation(**{"pass": True}, rule_ids=[], violations=[]),
    )
    return result.model_dump(by_alias=True)


def _failing_evaluation(department_id: str, violation: str = "currency_match: moneda incorrecta.") -> dict:
    from rfp_intake.evaluators import ComplianceEvaluation, ReadabilityEvaluation, RelevanceEvaluation

    result = combine_evaluation(
        department_id,
        ReadabilityEvaluation(**{"pass": True}, score=50.0, details="ok"),
        RelevanceEvaluation(**{"pass": True}, missing_aspects=[]),
        ComplianceEvaluation(**{"pass": False}, rule_ids=["currency_match"], violations=[violation]),
    )
    return result.model_dump(by_alias=True)


def test_succeeds_on_first_attempt_without_ever_calling_the_generator_again():
    def _refuse_to_regenerate(*args, **kwargs):
        raise AssertionError("no debería reintentar si la primera evaluación ya pasó")

    def evaluate_fn(department_id, client_country, key_aspects, draft_content):
        return _passing_evaluation(department_id)

    draft, evaluation, needs_human_review = _generate_and_evaluate_with_retries(
        "warehouse", "USA", {}, "borrador inicial", generator_fn=_refuse_to_regenerate, evaluate_fn=evaluate_fn
    )

    assert draft == "borrador inicial"
    assert evaluation["overall_pass"] is True
    assert needs_human_review is False


def test_retries_with_feedback_and_succeeds_on_second_attempt():
    calls: list[str | None] = []

    def generator_fn(key_aspects, client_country, feedback=None):
        calls.append(feedback)
        return f"borrador regenerado (intento {len(calls) + 1})"

    def evaluate_fn(department_id, client_country, key_aspects, draft_content):
        if draft_content == "borrador inicial":
            return _failing_evaluation(department_id)
        return _passing_evaluation(department_id)

    draft, evaluation, needs_human_review = _generate_and_evaluate_with_retries(
        "warehouse", "USA", {}, "borrador inicial", generator_fn=generator_fn, evaluate_fn=evaluate_fn
    )

    assert evaluation["overall_pass"] is True
    assert needs_human_review is False
    assert len(calls) == 1
    # El reintento debe haber recibido el feedback_for_generator REAL de la
    # evaluación fallida, no None ni un string vacío.
    assert calls[0] is not None
    assert "currency_match" in calls[0]


def test_escalates_to_needs_human_review_after_exhausting_the_iteration_limit():
    attempts = 0

    def generator_fn(key_aspects, client_country, feedback=None):
        nonlocal attempts
        attempts += 1
        return f"borrador intento {attempts}"

    def always_failing_evaluate_fn(department_id, client_country, key_aspects, draft_content):
        return _failing_evaluation(department_id)

    draft, evaluation, needs_human_review = _generate_and_evaluate_with_retries(
        "warehouse",
        "USA",
        {},
        "borrador inicial",
        generator_fn=generator_fn,
        evaluate_fn=always_failing_evaluate_fn,
        max_iterations=3,
    )

    assert needs_human_review is True
    assert evaluation["overall_pass"] is False
    # El último borrador y su evaluación real se conservan -- nunca se descarta la sección.
    assert draft is not None
    assert evaluation is not None
    # 3 iteraciones totales -> 2 regeneraciones (la primera usa initial_draft, no regenera).
    assert attempts == 2


def test_feedback_loop_with_the_real_generator_converges_within_the_iteration_limit():
    """Prueba de integración liviana (sin Postgres): el generador REAL de
    reverse, con una evaluación real, ya pasa en el primer intento porque
    es compliant-by-design -- confirma que el ciclo no reintenta sin
    necesidad cuando el generador real ya cumple."""

    key_aspects = {"estimated_return_rate_pct": 7}
    initial_draft = generate_reverse_section(key_aspects, "USA")

    def evaluate_fn(department_id, client_country, key_aspects_, draft_content):
        from rfp_intake.evaluators import evaluate_readability, evaluate_relevance

        readability = evaluate_readability(draft_content)
        relevance = evaluate_relevance(key_aspects_, draft_content)
        compliance = evaluate_compliance(department_id, client_country, draft_content)
        return combine_evaluation(department_id, readability, relevance, compliance).model_dump(by_alias=True)

    def generator_fn(key_aspects_, client_country, feedback=None):
        raise AssertionError("no debería reintentar -- el generador real ya es compliant-by-design")

    draft, evaluation, needs_human_review = _generate_and_evaluate_with_retries(
        "reverse", "USA", key_aspects, initial_draft, generator_fn=generator_fn, evaluate_fn=evaluate_fn
    )

    assert needs_human_review is False
    assert evaluation["overall_pass"] is True
