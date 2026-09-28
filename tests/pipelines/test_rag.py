"""Tests del RAG de TrackFlow (`CONTEXT/CONTEXT7.md`): Fase 1
(`data/process/rag.py` — chunking/indexación) y Fase 2
(`data/pipelines/rag.py` — `retrieve()`/`query()`/`generate_answer()`).

Usa Qdrant en modo `:memory:` (sin servidor real, sin Docker) y un
`embed_fn`/`generation_client` deterministas — no llama a ningún LLM real. La
correctitud de un embedding o una generación reales quedan fuera de esta
suite (necesitan credenciales de 4Geeks que este repo no trae, ver los
docstrings de `rag.py` en `data/process/` y `data/pipelines/`); lo que se
prueba acá es la lógica propia: parseo/chunking, la estructura del payload,
la idempotencia de `setup()`, el filtrado por `min_score` de `retrieve()`, y
que `query()` de verdad pasa por `generate_answer()` en vez de devolver texto
crudo de un chunk.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "data" / "process"))

import rag  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

# data/pipelines/rag.py se llama IGUAL que data/process/rag.py (ya importado
# arriba como "rag") -- se carga con importlib bajo un nombre explicito para
# no chocar, mismo motivo/patron documentado en data/pipelines/rag.py.
_PIPELINE_RAG_PATH = ROOT_DIR / "data" / "pipelines" / "rag.py"
_pipeline_spec = importlib.util.spec_from_file_location("trackflow_rag_pipeline", _PIPELINE_RAG_PATH)
pipeline_rag = importlib.util.module_from_spec(_pipeline_spec)
sys.modules["trackflow_rag_pipeline"] = pipeline_rag
_pipeline_spec.loader.exec_module(pipeline_rag)

FAKE_VECTOR_SIZE = 16
EXPECTED_SOURCE_DOCUMENTS = {"sla-delivery", "returns-policy", "carrier-coverage", "storage-pricing"}
REQUIRED_PAYLOAD_FIELDS = {"company", "source_document", "section", "language", "chunk_index", "text"}
TEST_COLLECTION = "test_trackflow_knowledge_retrieve"


def fake_embed(text: str) -> list[float]:
    """Vector determinista (hash de `text`), sin llamar a ningun LLM real."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:FAKE_VECTOR_SIZE]]


@pytest.fixture
def memory_client() -> QdrantClient:
    return QdrantClient(":memory:")


# --- Chunking -------------------------------------------------------------


def test_all_four_source_documents_exist_and_are_mapped():
    doc_paths = sorted(rag.KNOWLEDGE_BASE_DIR.glob("*.md"))
    filenames = {path.name for path in doc_paths}
    assert filenames == set(rag.SOURCE_DOCUMENT_BY_FILENAME.keys())
    assert {rag.SOURCE_DOCUMENT_BY_FILENAME[name] for name in filenames} == EXPECTED_SOURCE_DOCUMENTS


def test_each_document_produces_at_least_three_chunks():
    """CONTEXT7.md, Sección 5: "Cada documento debe producir al menos 3 chunks"."""
    for path in rag.KNOWLEDGE_BASE_DIR.glob("*.md"):
        chunks = rag.chunk_document(path)
        assert len(chunks) >= 3, f"{path.name} produjo {len(chunks)} chunks"


def test_chunks_are_self_contained_and_non_empty():
    for path in rag.KNOWLEDGE_BASE_DIR.glob("*.md"):
        for chunk in rag.chunk_document(path):
            assert chunk.text.strip()
            assert chunk.section in chunk.text  # el titulo de seccion esta antepuesto (autocontenido)


def test_chunk_index_is_sequential_and_zero_based_per_document():
    for path in rag.KNOWLEDGE_BASE_DIR.glob("*.md"):
        chunks = rag.chunk_document(path)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_split_into_chunks_never_cuts_mid_sentence():
    long_section = "Primera oración completa. " * 20 + "Segunda oración distinta con más palabras."
    pieces = rag.split_into_chunks(long_section, max_chars=100)

    assert len(pieces) > 1  # de verdad se dividio
    for piece in pieces:
        stripped = piece.strip()
        assert stripped.endswith(".")  # termina en limite de oracion, no a mitad de frase


def test_split_into_chunks_keeps_oversized_single_sentence_whole():
    """Una "oracion" (p. ej. una fila de tabla larga) que por si sola supera
    max_chars no se corta a la fuerza."""
    oversized_sentence = "x " * 200 + "fin."
    pieces = rag.split_into_chunks(oversized_sentence, max_chars=50)

    assert len(pieces) == 1
    assert pieces[0] == oversized_sentence


# --- setup() / indexación --------------------------------------------------


def test_setup_indexes_all_chunks_with_required_payload_fields(memory_client):
    collection = "test_trackflow_knowledge"
    indexed = rag.setup(qdrant_client=memory_client, embed_fn=fake_embed, collection_name=collection)

    info = memory_client.get_collection(collection)
    assert info.points_count == indexed

    points, _ = memory_client.scroll(collection_name=collection, limit=1000)
    assert len(points) == indexed

    seen_source_documents = set()
    for point in points:
        assert REQUIRED_PAYLOAD_FIELDS.issubset(point.payload.keys())
        assert point.payload["company"] == "trackflow"
        assert point.payload["language"] == "es"
        seen_source_documents.add(point.payload["source_document"])

    assert seen_source_documents == EXPECTED_SOURCE_DOCUMENTS


def test_setup_is_idempotent_on_rerun(memory_client):
    """Volver a correr setup() sobre los mismos documentos no duplica puntos
    (CONTEXT7.md, Sección "setup() debe ser idempotente")."""
    collection = "test_trackflow_knowledge_idempotent"

    first_count = rag.setup(qdrant_client=memory_client, embed_fn=fake_embed, collection_name=collection)
    first_points, _ = memory_client.scroll(collection_name=collection, limit=1000)
    first_ids = {p.id for p in first_points}

    second_count = rag.setup(qdrant_client=memory_client, embed_fn=fake_embed, collection_name=collection)
    second_points, _ = memory_client.scroll(collection_name=collection, limit=1000)
    second_ids = {p.id for p in second_points}

    assert first_count == second_count
    assert memory_client.get_collection(collection).points_count == first_count  # no crecio
    assert first_ids == second_ids  # mismos IDs deterministicos, no IDs nuevos


def test_chunk_point_id_is_deterministic_and_distinct_per_chunk():
    id_a = rag._chunk_point_id("trackflow", "sla-delivery", 0)
    id_a_again = rag._chunk_point_id("trackflow", "sla-delivery", 0)
    id_b = rag._chunk_point_id("trackflow", "sla-delivery", 1)
    id_other_doc = rag._chunk_point_id("trackflow", "returns-policy", 0)

    assert id_a == id_a_again
    assert len({id_a, id_b, id_other_doc}) == 3


def test_setup_raises_on_empty_source_dir(tmp_path, memory_client):
    with pytest.raises(FileNotFoundError):
        rag.setup(source_dir=tmp_path, qdrant_client=memory_client, embed_fn=fake_embed, collection_name="empty")


# --- Fase 2: retrieve() (data/pipelines/rag.py) -----------------------------


@pytest.fixture
def indexed_memory_client(memory_client) -> QdrantClient:
    """Qdrant :memory: ya indexado con los 4 documentos (fake_embed)."""
    rag.setup(qdrant_client=memory_client, embed_fn=fake_embed, collection_name=TEST_COLLECTION)
    return memory_client


def test_retrieve_returns_plain_dict_payloads_above_min_score(indexed_memory_client):
    """CONTEXT7.md, Fase 2: "devuelve solo los payloads ... no objetos crudos
    del SDK de Qdrant"."""
    points, _ = indexed_memory_client.scroll(collection_name=TEST_COLLECTION, limit=1)
    sample_text = points[0].payload["text"]

    # min_score=0.99 + la query es el texto EXACTO de un chunk -> con
    # fake_embed (hash determinista) el score de ese chunk es maximo.
    results = pipeline_rag.retrieve(
        sample_text,
        qdrant_client=indexed_memory_client,
        embed_fn=fake_embed,
        collection_name=TEST_COLLECTION,
        min_score=0.99,
    )

    assert len(results) >= 1
    assert all(type(result) is dict for result in results)  # nunca ScoredPoint u otro objeto del SDK
    assert results[0]["text"] == sample_text
    assert REQUIRED_PAYLOAD_FIELDS.issubset(results[0].keys())


def test_retrieve_filters_out_results_below_min_score(indexed_memory_client):
    """CONTEXT7.md, Fase 2: "filtra los que queden por debajo de min_score"."""
    results = pipeline_rag.retrieve(
        "una pregunta cualquiera",
        qdrant_client=indexed_memory_client,
        embed_fn=fake_embed,
        collection_name=TEST_COLLECTION,
        min_score=1.5,  # inalcanzable (similitud coseno <= 1.0)
    )
    assert results == []


def test_retrieve_can_return_fewer_than_k_results(indexed_memory_client):
    """CONTEXT7.md, Fase 2: "pueden devolver menos de k resultados"."""
    results = pipeline_rag.retrieve(
        "una pregunta cualquiera",
        qdrant_client=indexed_memory_client,
        embed_fn=fake_embed,
        collection_name=TEST_COLLECTION,
        k=5,
        min_score=1.5,
    )
    assert len(results) < 5


# --- Fase 2: generate_answer() / query() (data/pipelines/rag.py) -----------


class _FakeChatCompletionMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatCompletionChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeChatCompletionMessage(content)


class _FakeChatCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_call: dict[str, object] = {}

    def create(self, model, messages):
        self.last_call = {"model": model, "messages": messages}
        return type("FakeResponse", (), {"choices": [_FakeChatCompletionChoice(self._content)]})()


class _FakeOpenAIClient:
    def __init__(self, content: str = "respuesta generada por el modelo fake") -> None:
        self.chat = type("FakeChat", (), {"completions": _FakeChatCompletions(content)})()


def test_generate_answer_sends_system_prompt_and_context_to_the_generation_client():
    """El prompt de generacion debe instruir al modelo con la voz/audiencia
    del ticket (CONTEXT7.md, Fase 2) y usar solo el contexto recuperado."""
    fake_client = _FakeOpenAIClient()
    context = [
        {
            "source_document": "returns-policy",
            "section": "Ventana de devolución estándar",
            "text": "30 días naturales desde la entrega.",
        }
    ]

    answer = pipeline_rag.generate_answer("¿cuál es la ventana de devolución?", context, generation_client=fake_client)

    assert answer == "respuesta generada por el modelo fake"
    system_message, user_message = fake_client.chat.completions.last_call["messages"]
    assert system_message["role"] == "system"
    assert "TrackFlow" in system_message["content"]
    assert "inventar" in system_message["content"] or "inventes" in system_message["content"]
    assert user_message["role"] == "user"
    assert "30 días naturales" in user_message["content"]  # el contexto recuperado llego al prompt


def test_generate_answer_tells_the_model_to_say_so_when_context_is_empty():
    fake_client = _FakeOpenAIClient()
    pipeline_rag.generate_answer("¿algo no documentado?", [], generation_client=fake_client)

    _system_message, user_message = fake_client.chat.completions.last_call["messages"]
    assert "No se recuperó ningún fragmento" in user_message["content"]


def test_query_orchestrates_retrieve_then_generate_and_returns_model_output():
    """query() es la unica funcion que deben llamar consumidores externos:
    retrieve() -> generate_answer(), devolviendo la salida del modelo."""
    call_order: list[str] = []
    raw_chunk_text = "30 días naturales desde la entrega."

    def fake_retrieve(question: str):
        call_order.append("retrieve")
        assert question == "¿cuál es la ventana de devolución?"
        return [{"source_document": "returns-policy", "section": "Ventana", "text": raw_chunk_text}]

    def fake_generate(question: str, context: list[dict]):
        call_order.append("generate")
        assert context[0]["text"] == raw_chunk_text
        return "La ventana de devolución estándar es de 30 días naturales."

    answer = pipeline_rag.query("¿cuál es la ventana de devolución?", retrieve_fn=fake_retrieve, generate_fn=fake_generate)

    assert call_order == ["retrieve", "generate"]  # retrieve() antes que generate()
    assert answer == "La ventana de devolución estándar es de 30 días naturales."
    assert answer != raw_chunk_text  # nunca texto crudo de chunk sin pasar por generacion


def test_query_end_to_end_against_indexed_memory_qdrant(indexed_memory_client):
    """Integracion Fase 1 + Fase 2 juntas: retrieve() real contra Qdrant
    :memory: indexado, generate_answer() con cliente fake."""
    points, _ = indexed_memory_client.scroll(collection_name=TEST_COLLECTION, limit=1)
    sample_text = points[0].payload["text"]
    fake_client = _FakeOpenAIClient("respuesta final")

    def retrieve_fn(question: str):
        return pipeline_rag.retrieve(
            question, qdrant_client=indexed_memory_client, embed_fn=fake_embed, collection_name=TEST_COLLECTION, min_score=0.99
        )

    def generate_fn(question: str, context: list[dict]):
        return pipeline_rag.generate_answer(question, context, generation_client=fake_client)

    answer = pipeline_rag.query(sample_text, retrieve_fn=retrieve_fn, generate_fn=generate_fn)

    assert answer == "respuesta final"
    _system_message, user_message = fake_client.chat.completions.last_call["messages"]
    assert sample_text[:30] in user_message["content"]  # el chunk recuperado de verdad llego al prompt
