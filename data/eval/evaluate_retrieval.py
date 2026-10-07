"""RAG de TrackFlow — Fase 5b: mide Recall@3 de `retrieve()` contra
`data/eval/test-queries.json` (`CONTEXT/CONTEXT7.md`, Sección 4: "al menos
el 80% de las preguntas de prueba deben tener el chunk correcto entre los 3
primeros resultados recuperados").

## Por qué esto NO usa el modelo de embeddings real de 4Geeks

Este repo no trae credenciales reales de 4Geeks (ver
`docs/rag/rag-design.md`) — sin ellas no se puede medir Recall@3 contra el
modelo que realmente correrá en producción. En vez de inventar un número
(lo que la propia guía prohíbe explícitamente para las respuestas del
sistema, y sería igual de deshonesto acá), este script usa un embedding
**local, determinista y lexicográfico** (`lexical_embed()`: vector de
frecuencia de término, normalizado L2, sobre el vocabulario de los 4
documentos + las preguntas de prueba) — no pretende ser semánticamente
equivalente al modelo real, pero sí mide algo real: si `retrieve()` (Fase 2,
sin cambios) puede encontrar el chunk correcto cuando pregunta y chunk
comparten vocabulario, que es como se redactaron las preguntas de
`test-queries.json` a propósito.

**Este resultado debe volver a correrse con `embed()` real en cuanto existan
credenciales de 4Geeks** (cambiar `embed_fn=lexical_embed` por
`embed_fn=real_embed` en `run()`) — el número que imprime este script hoy
mide la mecánica de recuperación (Qdrant + `retrieve()` + `min_score`), no
la calidad semántica del modelo de embeddings real.

Ejecución: `python data/eval/evaluate_retrieval.py` (usa el venv de
`data/process/`: `source ../process/.venv/bin/activate` primero, o
`cd data/process && uv run ../eval/evaluate_retrieval.py`).
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable

from qdrant_client import QdrantClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TEST_QUERIES_PATH = ROOT_DIR / "data" / "eval" / "test-queries.json"
RESULTS_PATH = ROOT_DIR / "data" / "eval" / "retrieval_recall.json"
EVAL_COLLECTION = "trackflow_knowledge_eval_lexical"
RECALL_K = 3
RECALL_THRESHOLD = 0.80  # CONTEXT7.md Seccion 4

# Mismo motivo de colision de nombres que data/pipelines/rag.py: ambos
# modulos se llaman "rag.py".
_INDEXING_PATH = ROOT_DIR / "data" / "process" / "rag.py"
_indexing_spec = importlib.util.spec_from_file_location("trackflow_rag_indexing_eval", _INDEXING_PATH)
indexing = importlib.util.module_from_spec(_indexing_spec)
sys.modules["trackflow_rag_indexing_eval"] = indexing
_indexing_spec.loader.exec_module(indexing)

_PIPELINE_PATH = ROOT_DIR / "data" / "pipelines" / "rag.py"
_pipeline_spec = importlib.util.spec_from_file_location("trackflow_rag_pipeline_eval", _PIPELINE_PATH)
pipeline = importlib.util.module_from_spec(_pipeline_spec)
sys.modules["trackflow_rag_pipeline_eval"] = pipeline
_pipeline_spec.loader.exec_module(pipeline)

_TOKEN_RE = re.compile(r"[a-záéíóúñü]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def build_vocabulary(*texts: str) -> list[str]:
    vocabulary: set[str] = set()
    for text in texts:
        vocabulary.update(_tokenize(text))
    return sorted(vocabulary)


def make_lexical_embed(vocabulary: list[str]) -> Callable[[str], list[float]]:
    """Vector de frecuencia de termino (TF), normalizado L2, sobre `vocabulary`.

    Con vectores L2-normalizados, similitud coseno == producto punto -- Qdrant
    (`Distance.COSINE`) lo calcula igual que con un embedding real.
    """
    index = {word: position for position, word in enumerate(vocabulary)}

    def embed(text: str) -> list[float]:
        counts = Counter(_tokenize(text))
        vector = [0.0] * len(vocabulary)
        for word, count in counts.items():
            position = index.get(word)
            if position is not None:
                vector[position] = float(count)
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    return embed


def load_test_queries(path: Path = TEST_QUERIES_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["queries"]


def compute_recall_at_k(
    queries: list[dict],
    embed_fn: Callable[[str], list[float]],
    qdrant_client: QdrantClient,
    collection_name: str = EVAL_COLLECTION,
    k: int = RECALL_K,
    min_score: float = pipeline.DEFAULT_MIN_SCORE,
) -> dict:
    """Para cada pregunta, busca el top-`k` (sin filtrar por `min_score`,
    Seccion 4 del CONTEXT: "entre los 3 primeros resultados recuperados" es
    sobre la busqueda vectorial en si) y marca "hit" si el chunk esperado
    (source_document + section) aparece. Tambien reporta, por separado,
    cuantos de esos hits sobrevivirian al `min_score` de produccion --
    informativo para calibrarlo, no parte del calculo de Recall@k en si."""
    details = []
    hits = 0
    hits_above_min_score = 0

    for query in queries:
        top_k = pipeline.retrieve(
            query["question"],
            k=k,
            min_score=-1.0,  # sin filtrar: Recall@k es sobre la busqueda vectorial cruda
            qdrant_client=qdrant_client,
            embed_fn=embed_fn,
            collection_name=collection_name,
        )
        matched_rank = next(
            (
                rank
                for rank, chunk in enumerate(top_k, start=1)
                if chunk["source_document"] == query["expected_source_document"] and chunk["section"] == query["expected_section"]
            ),
            None,
        )
        hit = matched_rank is not None
        hits += hit

        above_min_score = False
        if hit:
            above_min_score = any(
                chunk["source_document"] == query["expected_source_document"]
                and chunk["section"] == query["expected_section"]
                for chunk in pipeline.retrieve(
                    query["question"],
                    k=k,
                    min_score=min_score,
                    qdrant_client=qdrant_client,
                    embed_fn=embed_fn,
                    collection_name=collection_name,
                )
            )
        hits_above_min_score += above_min_score

        details.append(
            {
                "id": query["id"],
                "question": query["question"],
                "expected": f"{query['expected_source_document']} / {query['expected_section']}",
                "hit": hit,
                "hit_rank": matched_rank,
                "survives_min_score": above_min_score,
                "retrieved": [f"{c['source_document']} / {c['section']}" for c in top_k],
            }
        )

    total = len(queries)
    return {
        "recall_at_k": hits / total,
        "k": k,
        "hits": hits,
        "total": total,
        "hits_surviving_min_score": hits_above_min_score,
        "min_score_used_for_secondary_check": min_score,
        "details": details,
    }


def run() -> dict:
    queries = load_test_queries()

    all_chunk_texts = [
        chunk.text for path in sorted(indexing.KNOWLEDGE_BASE_DIR.glob("*.md")) for chunk in indexing.chunk_document(path)
    ]
    vocabulary = build_vocabulary(*all_chunk_texts, *[q["question"] for q in queries])
    lexical_embed = make_lexical_embed(vocabulary)

    client = QdrantClient(":memory:")
    indexing.setup(qdrant_client=client, embed_fn=lexical_embed, collection_name=EVAL_COLLECTION)

    result = compute_recall_at_k(queries, lexical_embed, client)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    outcome = run()
    print(f"Recall@{outcome['k']}: {outcome['recall_at_k']:.0%} ({outcome['hits']}/{outcome['total']})")
    print(f"De esos hits, sobreviven al min_score de producción ({outcome['min_score_used_for_secondary_check']}): {outcome['hits_surviving_min_score']}/{outcome['hits']}")
    for row in outcome["details"]:
        marker = "OK" if row["hit"] else "MISS"
        print(f"  [{marker}] {row['id']}: {row['question']!r} -> esperado {row['expected']!r}, hit_rank={row['hit_rank']}")
    if outcome["recall_at_k"] < RECALL_THRESHOLD:
        print(f"\nADVERTENCIA: Recall@{outcome['k']} ({outcome['recall_at_k']:.0%}) por debajo del umbral de CONTEXT7.md ({RECALL_THRESHOLD:.0%}).")
    print(f"\nResultados completos en {RESULTS_PATH}")
