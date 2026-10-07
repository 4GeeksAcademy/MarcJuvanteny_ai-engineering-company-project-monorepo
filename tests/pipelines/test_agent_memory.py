"""Evals de memoria y auto-mejora del agente (`CONTEXT/CONTEXT8.md`, Hito 8
Parte 1). Corren sin Redis real (`fakeredis`, misma API que `redis-py`) y
sin credenciales de 4Geeks (heurísticas deterministas para self-eval y
clasificación de decisión, mismo patrón que `classify_intent` en
Hito 7) -- ver `services/knowledge-api/memory_store.py`/`memory_proposal.py`/
`memory_decision.py` para el porqué de cada stand-in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "services" / "knowledge-api"))

import agent_graph  # noqa: E402
from memory_audit import read_audit_log  # noqa: E402
from memory_decision import classify_memory_decision  # noqa: E402
from memory_proposal import evaluate_for_memory_proposal  # noqa: E402
from memory_store import (  # noqa: E402
    MemoryEntry,
    enforce_memory_capacity,
    list_memory_keys,
    make_entry,
    read_memory,
    write_memory,
)


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def fake_redis():
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeRedis(decode_responses=True)


def _echo_generate(question: str, context: list[dict]) -> str:
    return " | ".join(chunk["text"] for chunk in context) if context else "sin contexto"


def _refuse_to_be_called(*args, **kwargs):
    raise AssertionError("esta funcion no deberia haberse llamado en este escenario")


# --- memory_store.py: interfaz explícita de lectura/escritura --------------


def test_write_then_read_roundtrip(fake_redis):
    entry = make_entry("SEUR:Spain", "carrier_rule", "SEUR ya no cubre la zona rural.", source_thread_id="t1")
    write_memory(entry, client=fake_redis)

    read_back = read_memory("SEUR:Spain", client=fake_redis)

    assert read_back == entry


def test_read_missing_key_returns_none_not_an_error(fake_redis):
    assert read_memory("DHL Express:USA", client=fake_redis) is None


def test_write_consolidates_by_key_not_appends(fake_redis):
    """`CONTEXT8.md`, "Consolidación sugerida": por carrier+país, no por
    ticket individual -- un segundo write para la misma clave reemplaza,
    no apila."""

    first = make_entry("Nacex:Spain", "carrier_rule", "Nacex cubre Aragón rural.", source_thread_id="t1")
    second = make_entry("Nacex:Spain", "carrier_rule", "Nacex ya NO cubre Aragón rural desde marzo.", source_thread_id="t2")

    write_memory(first, client=fake_redis)
    write_memory(second, client=fake_redis)

    result = read_memory("Nacex:Spain", client=fake_redis)
    assert result.fact == second.fact
    assert result.source_thread_id == "t2"


def test_make_entry_rejects_unknown_category():
    with pytest.raises(ValueError):
        make_entry("x:y", "not_a_real_category", "fact", source_thread_id="t1")


def test_memory_entry_is_isolated_from_qdrant_rag_namespace(fake_redis):
    """No es un test de Qdrant (no está disponible acá) -- confirma que el
    namespace de claves nunca podría colisionar con `trackflow_knowledge`:
    todo lo que escribe `write_memory` vive bajo el prefijo `agent_memory:`,
    nunca un nombre de colección RAG."""

    entry = make_entry("UPS Ground:USA", "carrier_rule", "fact", source_thread_id="t1")
    write_memory(entry, client=fake_redis)

    raw_keys = [k for k in fake_redis.keys("*")]
    assert all(k.startswith("agent_memory:") for k in raw_keys)
    assert "trackflow_knowledge" not in raw_keys


# --- memory_store.py: Consolidación y Limpieza (expiración + capacidad) ----


def test_write_memory_sets_a_ttl(fake_redis):
    entry = make_entry("SEUR:Spain", "carrier_rule", "fact", source_thread_id="t1")
    write_memory(entry, client=fake_redis)

    ttl = fake_redis.ttl("agent_memory:SEUR:Spain")
    assert ttl > 0  # tiene expiracion, no vive para siempre


def test_write_memory_renews_ttl_on_reconfirmation(fake_redis):
    """Re-escribir la misma clave (una corrección/edición) renueva el TTL
    -- una regla que se sigue usando y corrigiendo nunca expira por
    accidente."""

    entry = make_entry("SEUR:Spain", "carrier_rule", "fact v1", source_thread_id="t1")
    write_memory(entry, client=fake_redis)
    fake_redis.expire("agent_memory:SEUR:Spain", 5)  # simula que ya casi expiraba

    updated = make_entry("SEUR:Spain", "carrier_rule", "fact v2", source_thread_id="t2")
    write_memory(updated, client=fake_redis)

    assert fake_redis.ttl("agent_memory:SEUR:Spain") > 5


def test_enforce_memory_capacity_evicts_oldest_updated_entries_beyond_the_cap(fake_redis):
    """"Mecanismo de consolidación que evite que la memoria crezca sin
    control... descartar entradas de baja relevancia" -- la entrada con
    `updated_at` más antiguo se descarta primero."""

    import time

    for i in range(5):
        entry = make_entry(f"client_preference:client{i}", "client_preference", f"fact {i}", source_thread_id="t1")
        write_memory(entry, client=fake_redis, enforce_capacity=False)
        time.sleep(0.01)  # asegura updated_at estrictamente creciente entre entradas

    evicted = enforce_memory_capacity(max_entries=3, client=fake_redis)

    assert set(evicted) == {"client_preference:client0", "client_preference:client1"}
    remaining = set(list_memory_keys(client=fake_redis))
    assert remaining == {"client_preference:client2", "client_preference:client3", "client_preference:client4"}


def test_enforce_memory_capacity_is_a_noop_under_the_cap(fake_redis):
    entry = make_entry("SEUR:Spain", "carrier_rule", "fact", source_thread_id="t1")
    write_memory(entry, client=fake_redis, enforce_capacity=False)

    evicted = enforce_memory_capacity(max_entries=200, client=fake_redis)

    assert evicted == []
    assert read_memory("SEUR:Spain", client=fake_redis) is not None


def test_write_memory_triggers_capacity_enforcement_automatically(fake_redis):
    """`write_memory` dispara `enforce_memory_capacity` por defecto -- un
    caller no tiene que acordarse de llamarla aparte."""

    import time

    for i in range(4):
        entry = make_entry(f"client_preference:client{i}", "client_preference", f"fact {i}", source_thread_id="t1")
        # max_entries=3 en cada write: el 4to write por si solo ya deberia
        # disparar el desalojo del mas antiguo, sin llamar enforce_memory_capacity() aparte.
        write_memory(entry, client=fake_redis, max_entries=3)
        time.sleep(0.01)

    remaining = set(list_memory_keys(client=fake_redis))
    assert len(remaining) == 3
    assert "client_preference:client0" not in remaining  # el mas viejo, desalojado


# --- memory_proposal.py: auto-evaluación, exactamente lo que pide CONTEXT8 -


@pytest.mark.parametrize(
    "question",
    [
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.",
        "Esos retrasos reportados en incidencias de Los Ángeles esta semana son por la huelga portuaria, "
        "no por un problema nuestro — ya van tres tickets sobre lo mismo.",
        "El cliente de cosméticos siempre quiere su reporte mensual con el desglose de devoluciones primero, "
        "antes que el volumen de envíos.",
    ],
)
def test_eval_examples_that_should_generate_a_proposal(question: str):
    """Los 3 ejemplos literales de `CONTEXT8.md`, "Ejemplos para tu
    checklist de Auto-evaluación"."""

    proposal = evaluate_for_memory_proposal(question, "")
    assert proposal is not None
    assert proposal.category in ("carrier_rule", "incident_context", "client_preference")


@pytest.mark.parametrize(
    "question",
    [
        "¿Dónde está el paquete con tracking XJ4471?",
        "Perfecto, ya quedó resuelto.",
        "Tradúceme esto al inglés para el cliente.",
    ],
)
def test_eval_examples_that_should_not_generate_a_proposal(question: str):
    """Los 3 ejemplos literales de `CONTEXT8.md` que NO deberían proponer
    nada -- consulta puntual, cierre de conversación, tarea de un solo uso."""

    assert evaluate_for_memory_proposal(question, "") is None


@pytest.mark.parametrize(
    "question",
    [
        "Apunta la dirección del cliente: Calle Mayor 12, para la próxima entrega.",
        "Recuerda la ruta interna del almacén para ese pasillo.",
        "Recuerda que SEUR tuvo un retraso puntual con el tracking AB1234 ayer.",
        "Estamos en negociación de contrato con este cliente, no cierres nada todavía.",
    ],
)
def test_eval_forbidden_content_never_proposed_even_if_pattern_matches(question: str):
    """`CONTEXT8.md`, "Qué NUNCA debe entrar en la memoria" -- el filtro de
    contenido prohibido corre SIEMPRE, incluso cuando el texto también
    dispara un patrón de categoría permitida."""

    assert evaluate_for_memory_proposal(question, "") is None


def test_proposal_key_consolidates_by_carrier_and_country():
    proposal = evaluate_for_memory_proposal(
        "SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.", ""
    )
    assert proposal.key == "SEUR:Spain"


def test_proposal_country_comes_from_the_carrier_not_just_city_names_in_the_text():
    """Bug real encontrado documentando la "Evidencia" de esta entrega:
    "Aragón" (sin mencionar "Zaragoza") no disparaba el heurístico de texto
    -- Nacex es un carrier exclusivo de España, el país debe salir del
    carrier mismo, no de adivinar nombres de ciudad."""

    proposal = evaluate_for_memory_proposal(
        "En realidad Nacex ya no cubre esa zona rural de Aragon, hay que usar el carrier local desde el mes pasado.",
        "",
    )
    assert proposal.key == "Nacex:Spain"


# --- memory_decision.py: clasificación explícita, no "si" in mensaje -------


def test_decision_approved():
    assert classify_memory_decision("Sí, guárdalo.").outcome == "approved"


def test_decision_rejected_explicit():
    assert classify_memory_decision("No, no hace falta.").outcome == "rejected"


def test_decision_edited_carries_the_correction():
    decision = classify_memory_decision("Sí, pero en realidad es solo para pedidos urgentes.")
    assert decision.outcome == "edited"
    assert decision.edited_fact == "Sí, pero en realidad es solo para pedidos urgentes."


def test_decision_defaults_to_rejected_on_topic_change():
    """"Si el usuario cambia de tema sin responder claramente sí o no, la
    propuesta se descarta por defecto"."""

    decision = classify_memory_decision("¿Cuál es el estado del ticket 42?")
    assert decision.outcome == "rejected"


def test_naive_substring_match_would_have_misclassified_this():
    """Motiva por qué no alcanza un `"sí" in mensaje`: esta frase de rechazo
    contiene "sí" como substring de "así"."""

    decision = classify_memory_decision("No, no sé si eso es así.")
    assert decision.outcome == "rejected"


# --- Integración con el grafo: propuesta -> turno siguiente -> resolución --


@pytest.mark.anyio
async def test_turn_proposes_memory_within_the_same_answer():
    def fake_retrieve(question: str):
        return []

    recorded_writes = []
    recorded_audits = []

    state, trace, thread_id = await agent_graph.run_agent(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.",
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: recorded_writes.append(a),
        audit_memory_fn=lambda **kw: recorded_audits.append(kw),
        checkpointer=agent_graph.MemorySaver(),
    )

    assert state["pending_memory_proposal"] is not None
    assert "¿Querés que recuerde esto" in state["answer"]
    assert recorded_writes == []  # nunca escribe en el mismo paso que propone
    node_order = [step["node"] for step in trace]
    assert "propose_memory" in node_order
    assert "resolve_pending_memory_proposal" not in node_order  # no habia nada pendiente al empezar este turno


@pytest.mark.anyio
async def test_pending_proposal_survives_to_the_next_turn_and_gets_approved():
    checkpointer = agent_graph.MemorySaver()
    thread_id = "memory-approve-thread"
    recorded_writes = []
    recorded_audits = []

    def fake_retrieve(question: str):
        return []

    turn1_state, _trace1, _ = await agent_graph.run_agent(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.",
        thread_id=thread_id,
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: recorded_writes.append(a),
        audit_memory_fn=lambda **kw: recorded_audits.append(kw),
        checkpointer=checkpointer,
    )
    assert turn1_state["pending_memory_proposal"] is not None

    turn2_state, trace2, _ = await agent_graph.run_agent(
        "Sí, guárdalo.",
        thread_id=thread_id,
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: recorded_writes.append(a),
        audit_memory_fn=lambda **kw: recorded_audits.append(kw),
        checkpointer=checkpointer,
    )

    node_order2 = [step["node"] for step in trace2]
    assert node_order2[0:3] == ["receive_question", "input_guard", "resolve_pending_memory_proposal"]
    assert turn2_state["pending_memory_proposal"] is None  # resuelta, y "Si, guardalo" no genera una nueva
    assert len(recorded_writes) == 1
    assert recorded_writes[0][0] == "SEUR:Spain"  # key
    assert len(recorded_audits) == 1
    assert recorded_audits[0]["outcome"] == "approved"


@pytest.mark.anyio
async def test_pending_proposal_rejected_is_not_written_but_is_audited():
    checkpointer = agent_graph.MemorySaver()
    thread_id = "memory-reject-thread"
    recorded_writes = []
    recorded_audits = []

    def fake_retrieve(question: str):
        return []

    await agent_graph.run_agent(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.",
        thread_id=thread_id,
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: recorded_writes.append(a),
        audit_memory_fn=lambda **kw: recorded_audits.append(kw),
        checkpointer=checkpointer,
    )

    await agent_graph.run_agent(
        "No, eso no es correcto.",
        thread_id=thread_id,
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: recorded_writes.append(a),
        audit_memory_fn=lambda **kw: recorded_audits.append(kw),
        checkpointer=checkpointer,
    )

    assert recorded_writes == []  # rechazada: nunca se escribe
    assert len(recorded_audits) == 1  # pero SIEMPRE se audita, aprobada o no
    assert recorded_audits[0]["outcome"] == "rejected"


@pytest.mark.anyio
async def test_only_one_pending_proposal_at_a_time():
    """"Solo puede haber una propuesta pendiente a la vez: si ya hay una sin
    resolver, el agente no debe lanzar una segunda hasta cerrar la
    primera"."""

    checkpointer = agent_graph.MemorySaver()
    thread_id = "memory-single-pending-thread"

    def fake_retrieve(question: str):
        return []

    turn1_state, _, _ = await agent_graph.run_agent(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza, hay que usar el carrier local desde el mes pasado.",
        thread_id=thread_id,
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: None,
        audit_memory_fn=lambda **kw: None,
        checkpointer=checkpointer,
    )
    first_proposal_key = turn1_state["pending_memory_proposal"]["key"]

    # El usuario aprueba la primera Y, en el mismo mensaje, trae otra
    # observación memorable (otra regla de carrier) -- solo debe quedar UNA
    # propuesta pendiente al final (la nueva), nunca dos acumuladas.
    turn2_state, _, _ = await agent_graph.run_agent(
        "Sí, guárdalo. Por cierto, Nacex ya no opera esa ruta desde el mes pasado, hay que usar el carrier local.",
        thread_id=thread_id,
        retrieve_fn=fake_retrieve,
        generate_fn=_echo_generate,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        write_memory_fn=lambda *a: None,
        audit_memory_fn=lambda **kw: None,
        checkpointer=checkpointer,
    )

    assert turn2_state["pending_memory_proposal"] is not None
    assert turn2_state["pending_memory_proposal"]["key"] != first_proposal_key


@pytest.mark.anyio
async def test_retrieve_memory_injects_approved_fact_into_generation_context():
    """Lado de LECTURA de la interfaz explícita de memoria."""

    stored = make_entry(
        "SEUR:Spain", "carrier_rule", "SEUR ya no cubre la zona rural de Zaragoza.", source_thread_id="t0"
    )

    def fake_read(key: str):
        assert key == "SEUR:Spain"
        return stored

    state, trace, _ = await agent_graph.run_agent(
        "¿SEUR cubre la ruta rural de Zaragoza?",
        retrieve_fn=lambda q: [],
        generate_fn=_echo_generate,
        read_memory_fn=fake_read,
        incidents_tool_fn=_refuse_to_be_called,
        inventory_tool_fn=_refuse_to_be_called,
        checkpointer=agent_graph.MemorySaver(),
    )

    assert "SEUR ya no cubre la zona rural de Zaragoza." in state["answer"]
    assert "retrieve_memory" in [step["node"] for step in trace]


# --- memory_audit.py: registro real en disco --------------------------------


def test_record_memory_decision_is_appended_to_disk_and_readable(tmp_path, monkeypatch):
    import memory_audit

    fake_log_path = tmp_path / "agent-memory-audit.jsonl"
    monkeypatch.setattr(memory_audit, "AUDIT_LOG_PATH", fake_log_path)

    memory_audit.record_memory_decision(
        thread_id="t1",
        proposal={"key": "SEUR:Spain", "category": "carrier_rule", "fact": "x", "reason": "y"},
        outcome="approved",
        triggering_message="Sí, guárdalo.",
    )
    memory_audit.record_memory_decision(
        thread_id="t2",
        proposal={"key": "Nacex:Spain", "category": "carrier_rule", "fact": "x", "reason": "y"},
        outcome="rejected",
        triggering_message="No.",
    )

    records = memory_audit.read_audit_log()
    assert len(records) == 2
    assert {r["outcome"] for r in records} == {"approved", "rejected"}
    assert all("timestamp" in r for r in records)
