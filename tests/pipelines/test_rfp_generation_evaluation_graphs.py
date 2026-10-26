"""Pruebas del grafo de generación (fan-out dinámico por departamento) y
del grafo de evaluación (fan-out estático a los 3 evaluadores en
paralelo) -- `CONTEXT/CONTEXT9.md`, Hito 9 Parte 2, checklist "Pruebas".

Mismo patrón que `test_rfp_workers.py` (Parte 1): funciones inyectables
con `_refuse_to_be_called` para probar que un departamento no activo
nunca dispara su generador.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.evaluation_graph import build_evaluation_graph  # noqa: E402
from rfp_intake.evaluators import ComplianceEvaluation, ReadabilityEvaluation, RelevanceEvaluation  # noqa: E402
from rfp_intake.generation_graph import build_generation_graph  # noqa: E402
from rfp_intake.generators import generate_warehouse_section  # noqa: E402


def _refuse_to_be_called(*args, **kwargs):
    raise AssertionError("esta funcion no deberia haberse llamado en este escenario")


# --- grafo de generación: fan-out a SOLO los departamentos activos ---------------------


def test_generation_graph_only_runs_generators_for_departments_needed():
    compiled = build_generation_graph(lastmile_generator_fn=_refuse_to_be_called)

    result = compiled.invoke(
        {
            "client_country": "Spain",
            "departments_needed": ["warehouse", "reverse"],
            "warehouse_key_aspects": {"monthly_volume": 3000, "client_country": "Spain"},
            "reverse_key_aspects": {"estimated_return_rate_pct": 7},
        }
    )

    assert result["warehouse_draft"] is not None
    assert result["reverse_draft"] is not None
    assert result.get("lastmile_draft") is None


def test_generation_graph_runs_a_single_generator_when_only_one_department_is_needed():
    compiled = build_generation_graph(
        lastmile_generator_fn=_refuse_to_be_called,
        reverse_generator_fn=_refuse_to_be_called,
    )

    result = compiled.invoke(
        {
            "client_country": "USA",
            "departments_needed": ["warehouse"],
            "warehouse_key_aspects": {"monthly_volume": 1200, "client_country": "USA"},
        }
    )

    assert result["warehouse_draft"] is not None
    assert result.get("lastmile_draft") is None
    assert result.get("reverse_draft") is None


# --- grafo de evaluación: SIEMPRE corren los 3 evaluadores en paralelo, convergen en 1 --


def test_evaluation_graph_runs_all_three_evaluators_and_combines_into_one_result():
    compiled = build_evaluation_graph()
    key_aspects = {"monthly_volume": 3000, "client_country": "USA"}

    result = compiled.invoke(
        {
            "department_id": "warehouse",
            "client_country": "USA",
            "key_aspects": key_aspects,
            "draft_content": generate_warehouse_section(key_aspects, "USA"),
        }
    )

    assert result["readability_result"] is not None
    assert result["relevance_result"] is not None
    assert result["compliance_result"] is not None
    assert result["evaluation_result"] is not None
    assert result["evaluation_result"]["overall_pass"] is True


def test_evaluation_graph_combine_uses_injected_evaluations_not_recomputed_ones():
    """Las 3 ramas corren con las funciones INYECTADAS -- el combine lee
    los resultados ya calculados, nunca vuelve a evaluar nada."""

    compiled = build_evaluation_graph(
        evaluate_readability_fn=lambda draft: ReadabilityEvaluation(**{"pass": False}, score=1.0, details="forzado a fallar"),
        evaluate_relevance_fn=lambda key_aspects, draft: RelevanceEvaluation(**{"pass": True}, missing_aspects=[]),
        evaluate_compliance_fn=lambda dept, country, draft: ComplianceEvaluation(
            **{"pass": True}, rule_ids=[], violations=[]
        ),
    )

    result = compiled.invoke(
        {
            "department_id": "warehouse",
            "client_country": "USA",
            "key_aspects": {},
            "draft_content": "cualquier texto",
        }
    )

    assert result["evaluation_result"]["readability"]["pass"] is False
    assert result["evaluation_result"]["overall_pass"] is False
