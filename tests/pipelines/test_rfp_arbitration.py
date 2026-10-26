"""Pruebas del nodo de arbitraje (`CONTEXT/CONTEXT9.md` Sección 7, Hito 9
Parte 3) -- los 3 triggers deterministas y sus árbitros fijos. Corren con
secciones sintéticas (nunca un LLM "negociando" entre agentes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake.arbitration import (  # noqa: E402
    MIGUEL_TORRES,
    SOFIA_RAMOS,
    WAREHOUSE_MAX_MONTHLY_CAPACITY,
    check_currency_mismatch,
    check_returns_sla_breach,
    check_volume_vs_capacity,
    run_arbitration,
)


def test_volume_vs_capacity_does_not_trigger_within_capacity():
    sections = {
        "warehouse": {"key_aspects": {"monthly_volume": WAREHOUSE_MAX_MONTHLY_CAPACITY}},
        "lastmile": {"key_aspects": {}},
    }
    assert check_volume_vs_capacity(sections) is None


def test_volume_vs_capacity_triggers_and_names_miguel_torres():
    sections = {
        "warehouse": {"key_aspects": {"monthly_volume": WAREHOUSE_MAX_MONTHLY_CAPACITY + 1000}},
        "lastmile": {"key_aspects": {}},
    }
    decision = check_volume_vs_capacity(sections)
    assert decision is not None
    assert decision.trigger_id == "volume-vs-capacity"
    assert decision.arbiter == MIGUEL_TORRES
    assert set(decision.affected_departments) == {"warehouse", "lastmile"}


def test_volume_vs_capacity_only_applies_when_lastmile_is_also_active():
    """"Capacidad... no soporta el volumen asumido por lastmile" -- sin
    lastmile activo no hay conflicto que arbitrar entre departamentos."""

    sections = {"warehouse": {"key_aspects": {"monthly_volume": 9000}}}
    assert check_volume_vs_capacity(sections) is None


def test_returns_sla_breach_triggers_on_reverse_alone_and_names_sofia_ramos():
    sections = {"reverse": {"draft_content": "Tiempo de procesamiento de devoluciones comprometido: 24 horas."}}
    decision = check_returns_sla_breach(sections)
    assert decision is not None
    assert decision.trigger_id == "returns-sla-breach"
    assert decision.arbiter == SOFIA_RAMOS
    assert decision.affected_departments == ["reverse"]


def test_returns_sla_breach_escalates_to_miguel_torres_when_another_department_embeds_the_promise():
    sections = {
        "reverse": {"draft_content": "Sin promesas de horario acá."},
        "lastmile": {"draft_content": "Procesamos devoluciones en 12 horas, más rápido que nadie."},
    }
    decision = check_returns_sla_breach(sections)
    assert decision is not None
    assert decision.arbiter == MIGUEL_TORRES
    assert decision.affected_departments == ["lastmile"]


def test_returns_sla_breach_does_not_trigger_on_compliant_text():
    sections = {"reverse": {"draft_content": "Tiempo de procesamiento de devoluciones comprometido: 72 horas."}}
    assert check_returns_sla_breach(sections) is None


def test_currency_mismatch_triggers_when_draft_uses_wrong_currency_for_client_country():
    sections = {"warehouse": {"draft_content": "Costo cotizado en EUR."}}
    decision = check_currency_mismatch(sections, "USA")
    assert decision is not None
    assert decision.trigger_id == "currency-mismatch"
    assert decision.arbiter == MIGUEL_TORRES
    assert decision.affected_departments == ["warehouse"]


def test_currency_mismatch_does_not_trigger_when_currency_matches_client_country():
    sections = {"warehouse": {"draft_content": "Costo cotizado en USD."}}
    assert check_currency_mismatch(sections, "USA") is None


def test_run_arbitration_returns_empty_list_for_a_clean_proposal():
    sections = {
        "warehouse": {"key_aspects": {"monthly_volume": 1000}, "draft_content": "Costo cotizado en USD."},
        "lastmile": {"draft_content": "SLA de entrega a tiempo comprometido por TrackFlow: 95%. Costo cotizado en USD."},
    }
    assert run_arbitration(sections, "USA") == []


def test_run_arbitration_can_return_multiple_simultaneous_triggers():
    sections = {
        "warehouse": {"key_aspects": {"monthly_volume": 9000}, "draft_content": "Costo cotizado en EUR."},
        "lastmile": {"key_aspects": {}, "draft_content": "Costo cotizado en EUR."},
        "reverse": {"key_aspects": {}, "draft_content": "Devoluciones procesadas en 10 horas."},
    }
    triggered = run_arbitration(sections, "USA")
    trigger_ids = {d.trigger_id for d in triggered}
    assert trigger_ids == {"volume-vs-capacity", "currency-mismatch", "returns-sla-breach"}
