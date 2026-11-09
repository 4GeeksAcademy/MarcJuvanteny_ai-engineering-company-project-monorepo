"""Redacción de secciones RFP con LLM (`rfp_intake/generators.py`,
`_llm_narrative`): el modelo solo redacta el párrafo descriptivo, las
cifras comerciales siguen saliendo de la plantilla, y cualquier fallo o
texto fuera de contrato cae a la plantilla. Sin red: `httpx.post` simulado."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "pipelines"))

from rfp_intake import generators  # noqa: E402
from rfp_intake.evaluators import evaluate_compliance, evaluate_relevance  # noqa: E402

WAREHOUSE_ASPECTS = {"client_country": "Spain", "monthly_volume": 3200}
GOOD_TEXT = (
    "En TrackFlow gestionaremos su operativa en España con un volumen mensual de 3.200 pedidos, "
    "con control de inventario en tiempo real y una preparación de pedidos pensada para crecer con "
    "usted. Recibimos, almacenamos y preparamos cada pedido con procesos estables y visibles.\n\n"
    "El valor para su negocio es una logística predecible, sin inversiones propias y con un equipo "
    "que conoce el mercado español."
)


class _FakeResponse:
    def __init__(self, text: str):
        self._text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._text}}]}


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setattr(generators, "_llm_unavailable_until", 0.0)
    monkeypatch.setenv("RFP_LLM_ENABLED", "1")
    monkeypatch.setenv("GENERATION_API_KEY", "test-key")
    monkeypatch.setenv("GENERATION_MODEL", "test-model")
    monkeypatch.setenv("GENERATION_API_BASE", "https://llm.example/v1")


def _fake_post(responses: list):
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        item = responses[min(len(calls), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)

    return post, calls


def test_llm_disabled_by_default_uses_template(monkeypatch):
    monkeypatch.delenv("RFP_LLM_ENABLED", raising=False)
    called = []
    monkeypatch.setattr(generators.httpx, "post", lambda *a, **k: called.append(1))

    draft = generators.generate_warehouse_section(WAREHOUSE_ASPECTS, "Spain")

    assert not called
    assert "gestionaría el almacenamiento" in draft


def test_llm_narrative_replaces_template_paragraph_and_keeps_terms(llm_env, monkeypatch):
    post, calls = _fake_post([GOOD_TEXT])
    monkeypatch.setattr(generators.httpx, "post", post)

    draft = generators.generate_warehouse_section(WAREHOUSE_ASPECTS, "Spain")

    assert len(calls) == 1
    assert "3.200 pedidos" in draft
    assert "gestionaría el almacenamiento" not in draft
    # Las cifras comerciales siguen viniendo de la plantilla.
    assert "Tabla de descuentos por volumen" in draft
    assert evaluate_compliance("warehouse", "Spain", draft).passed
    assert evaluate_relevance(WAREHOUSE_ASPECTS, draft).passed


@pytest.mark.parametrize(
    "bad_text",
    [
        GOOD_TEXT + " Le ofrecemos un ahorro del 25 %.",  # cifra inventada
        GOOD_TEXT + " Precios desde 3 EUR.",  # moneda
        GOOD_TEXT + " Trabajamos con SEUR.",  # transportista concreto
    ],
)
def test_out_of_contract_text_falls_back_to_template(llm_env, monkeypatch, bad_text):
    post, calls = _fake_post([bad_text])
    monkeypatch.setattr(generators.httpx, "post", post)

    draft = generators.generate_warehouse_section(WAREHOUSE_ASPECTS, "Spain")

    assert len(calls) == 2  # un reintento antes de rendirse
    assert "gestionaría el almacenamiento" in draft


def test_provider_error_retries_then_succeeds(llm_env, monkeypatch):
    post, calls = _fake_post([TimeoutError("lento"), GOOD_TEXT])
    monkeypatch.setattr(generators.httpx, "post", post)

    draft = generators.generate_warehouse_section(WAREHOUSE_ASPECTS, "Spain")

    assert len(calls) == 2
    assert "3.200 pedidos" in draft


def test_feedback_is_sent_to_the_model_as_data(llm_env, monkeypatch):
    post, calls = _fake_post([GOOD_TEXT])
    monkeypatch.setattr(generators.httpx, "post", post)

    generators.generate_warehouse_section(WAREHOUSE_ASPECTS, "Spain", feedback="Legibilidad: simplifica.")

    user_message = calls[0]["messages"][1]["content"]
    assert "<feedback>" in user_message and "Legibilidad: simplifica." in user_message


def test_trackflow_commitments_are_citable(llm_env, monkeypatch):
    text = GOOD_TEXT.replace("3.200 pedidos", "un compromiso de entrega a tiempo del 95 %")
    post, _ = _fake_post([text])
    monkeypatch.setattr(generators.httpx, "post", post)

    draft = generators.generate_lastmile_section({"destination_country": "USA"}, "USA")

    assert "95 %" in draft.splitlines()[1]


def test_timeout_falls_back_immediately_and_pauses_the_llm(llm_env, monkeypatch):
    import httpx

    post, calls = _fake_post([httpx.ReadTimeout("lento"), GOOD_TEXT])
    monkeypatch.setattr(generators.httpx, "post", post)

    first = generators.generate_warehouse_section(WAREHOUSE_ASPECTS, "Spain")
    second = generators.generate_reverse_section({"estimated_return_rate_pct": 18}, "Spain")

    # Sin reintento tras un timeout, y la siguiente seccion ni siquiera llama al proveedor.
    assert len(calls) == 1
    assert "gestionaría el almacenamiento" in first
    assert "gestionaría la recepción" in second
