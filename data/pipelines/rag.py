"""RAG de TrackFlow — Fase 2: pipeline de recuperación y generación.

Implementa `CONTEXT/CONTEXT7.md`, Fase 2. Reutiliza `embed()` y
`COLLECTION_NAME` de `data/process/rag.py` (Fase 1, ver
`Pasos/rag-knowledge-base-fase1.md`) — la misma función de embeddings se usa
para indexar los chunks y para la pregunta del usuario, tal como exige la
guía. Se carga con `importlib` (no `sys.path.insert` + `import rag`) porque
ese módulo **también** se llama `rag.py`: insertar ambos paquetes en
`sys.path` a la vez haría que `import rag` fuera ambiguo según el orden de
`sys.path` — `importlib` con un nombre de módulo explícito evita esa
colisión sin renombrar ninguno de los dos archivos.

`query(question: str) -> str` es la **única** función que deben llamar
consumidores externos (el endpoint FastAPI de Fase 3,
`services/knowledge-api/`). `retrieve()` y `generate_answer()` (armado del
prompt + llamada al LLM) quedan como pasos separados y ambos inyectables
(`retrieve_fn`/`generate_fn` en `query()`, `qdrant_client`/`embed_fn` en
`retrieve()`, `generation_client` en `generate_answer()`) — un agente futuro
(LangGraph) puede reutilizar `retrieve()` y `generate_answer()` como pasos
independientes sin ejecutar los dos ni ninguno de los dos veces, y sin esa
inyección esta Fase no se podría probar sin credenciales reales de 4Geeks
(ver `tests/pipelines/test_rag.py`).

## Modelo de generación vs. modelo de embeddings

`generate_answer()` usa un modelo de **chat/completion** (`GENERATION_MODEL`,
`GENERATION_API_BASE`, `GENERATION_API_KEY` en `.env`) — nunca el modelo de
embeddings de `retrieve()`. Son variables de entorno completamente separadas
de las de Fase 1, tal como exige la guía.

## Umbral mínimo de similitud (`DEFAULT_MIN_SCORE`)

`docs/rag/rag-design.md` (Fase 1) dejó este umbral pendiente por no tener
embeddings reales para calibrarlo. Para esta entrega se fija en **0.5**
como punto de partida razonable, no como un valor validado empíricamente:
0.5 es el punto medio del rango [-1, 1] de similitud coseno (o [0, 1] para
embeddings normalizados no-negativos, el caso típico de modelos tipo
`text-embedding-3-*`), un umbral conservador que exige que el chunk
recuperado se parezca *más* a la pregunta que a un texto aleatorio antes de
usarlo como contexto, sin ser tan estricto como para descartar coincidencias
razonables por una redacción distinta entre la pregunta y el documento.
**Pendiente de recalibrar** corriendo `data/eval/test-queries.json` contra
el modelo de embeddings real y mirando la distribución de similitud de los
chunks correctos vs. incorrectos (documentado también como pendiente en
`Pasos/rag-knowledge-base-fase1.md`).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from qdrant_client import QdrantClient

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent.parent
load_dotenv(PACKAGE_DIR / ".env")

_INDEXING_MODULE_NAME = "trackflow_rag_indexing"
_INDEXING_MODULE_PATH = ROOT_DIR / "data" / "process" / "rag.py"
_spec = importlib.util.spec_from_file_location(_INDEXING_MODULE_NAME, _INDEXING_MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"No se pudo cargar {_INDEXING_MODULE_PATH}")
_indexing = importlib.util.module_from_spec(_spec)
# Registrar en sys.modules ANTES de exec_module(): sin esto, el @dataclass
# de data/process/rag.py (Chunk) falla al resolver `cls.__module__` via
# sys.modules durante su propio procesamiento -- es el paso que
# `importlib.import_module()` hace automaticamente y que hay que replicar a
# mano al cargar por spec_from_file_location() (bug real, encontrado al
# verificar este modulo contra un Qdrant real).
sys.modules[_INDEXING_MODULE_NAME] = _indexing
_spec.loader.exec_module(_indexing)

COLLECTION_NAME: str = _indexing.COLLECTION_NAME
embed: Callable[[str], list[float]] = _indexing.embed

GENERATION_MODEL = os.environ.get("GENERATION_MODEL", "gpt-4o-mini")
DEFAULT_K = 5
DEFAULT_MIN_SCORE = 0.5  # ver "Umbral minimo de similitud" en el docstring del modulo

# Voz/audiencia del ticket (CONTEXT7.md Seccion 1): "un asistente que
# cualquier account manager pueda usar como lo haria un vendedor de
# TrackFlow en una llamada con un cliente: con datos exactos y sin
# prometer condiciones que no existen en los acuerdos estandar."
SYSTEM_PROMPT = """Sos el asistente de ventas interno de TrackFlow, una empresa de logística \
de última milla y gestión de almacenes con operaciones en Los Ángeles (EE. UU.) y Zaragoza \
(España). Un account manager te está usando en tiempo real durante una llamada con un cliente \
o marca prospecto — respondés con la misma precisión que usaría un vendedor de TrackFlow: \
datos exactos, y nunca prometés una condición que no esté en los acuerdos estándar.

Respondés SOLO con la información del CONTEXTO recuperado que se te da a continuación. Si el \
contexto no alcanza para responder con confianza, decilo explícitamente ("no tengo esa \
información en la base de conocimiento" o similar) en vez de inventar un porcentaje, una \
tarifa, un plazo o cualquier otro dato. Si la pregunta es sobre una excepción o un descuento \
que el contexto marca como sujeto a aprobación, decilo así — nunca lo presentes como una \
condición estándar."""


def _qdrant_client() -> QdrantClient:
    return QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))


def retrieve(
    query: str,
    *,
    k: int = DEFAULT_K,
    min_score: float = DEFAULT_MIN_SCORE,
    qdrant_client: QdrantClient | None = None,
    embed_fn: Callable[[str], list[float]] = embed,
    collection_name: str = COLLECTION_NAME,
) -> list[dict[str, Any]]:
    """Embebe `query`, busca los `k` vecinos más cercanos en Qdrant, y
    devuelve solo los payloads (nunca objetos crudos del SDK) que superan
    `min_score`. Puede devolver menos de `k` resultados, o ninguno."""
    client = qdrant_client or _qdrant_client()
    vector = embed_fn(query)

    results = client.query_points(
        collection_name=collection_name,
        query=vector,
        limit=k,
        with_payload=True,
    ).points

    return [dict(point.payload) for point in results if point.score >= min_score]


def _build_prompt(question: str, context: list[dict[str, Any]]) -> str:
    if not context:
        return (
            f"Pregunta del cliente: {question}\n\n"
            "No se recuperó ningún fragmento de la base de conocimiento con similitud suficiente."
        )

    context_block = "\n\n".join(
        f"[Fuente: {chunk['source_document']} — {chunk['section']}]\n{chunk['text']}" for chunk in context
    )
    return f"Contexto recuperado:\n\n{context_block}\n\nPregunta del cliente: {question}"


def generate_answer(
    question: str,
    context: list[dict[str, Any]],
    generation_client: Any = None,
    system_prompt: str | None = None,
) -> str:
    """Arma el prompt con el contexto recuperado y llama al LLM de
    GENERACIÓN (chat/completion — nunca el de embeddings). Paso separado de
    `retrieve()` a propósito, ver el docstring del módulo.

    `system_prompt`: si se omite, usa el `SYSTEM_PROMPT` de este módulo
    (la herramienta interna de Fase 3, `POST /knowledge/query`). El agente
    de `services/knowledge-api/agent_graph.py` (Hito 8 Parte 2,
    `CONTEXT8.2.md`) inyecta el suyo propio
    (`guardrails.py::AGENT_SYSTEM_PROMPT`) en vez de duplicar esta función
    -- misma función, system prompt distinto según quién la llama."""
    from openai import OpenAI

    client = generation_client or OpenAI(
        base_url=os.environ.get("GENERATION_API_BASE") or None,
        api_key=os.environ.get("GENERATION_API_KEY", ""),
    )
    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(question, context)},
        ],
    )
    return response.choices[0].message.content


def query(
    question: str,
    *,
    retrieve_fn: Callable[[str], list[dict[str, Any]]] = retrieve,
    generate_fn: Callable[[str, list[dict[str, Any]]], str] = generate_answer,
) -> str:
    """La única función que deben llamar consumidores externos. Orquesta
    `retrieve_fn` -> armado del prompt -> `generate_fn`, y devuelve la
    respuesta final como string."""
    context = retrieve_fn(question)
    return generate_fn(question, context)
