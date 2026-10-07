"""RAG de TrackFlow — Fase 1: preparación de datos e indexación.

Implementa `CONTEXT/CONTEXT7.md` (Hito 7 — RAG y Base de Conocimiento),
sección "Fase 1 — Preparación de datos e indexación (`data/process/`)":
`setup()` parsea los documentos fuente de `docs/company-knowledge-base/`,
los divide en chunks semánticos, genera un embedding por chunk con `embed()`
y los indexa en la colección Qdrant `trackflow_knowledge`.

Las Fases 2+ (recuperación, generación, endpoint, UI) no están implementadas
todavía — no fueron pedidas en esta entrega. Ver `docs/rag/rag-design.md` y
`Pasos/rag-knowledge-base-fase1.md` para el resto de la tabla de
responsabilidades sugerida por la guía.

## Documentos fuente: generados, no copiados

`CONTEXT7.md` (Sección 2) pide copiar los 4 documentos fuente desde
`00-general-contexts/trackflow/` — esa carpeta no existe en este repo (mismo
patrón que `Pasos/sales-forecast-model.md`: el material de referencia del
curso no llegó al monorepo del estudiante). Los 4 documentos se **redactaron
directamente** en `docs/company-knowledge-base/`, con el contenido de negocio
(SLA, devoluciones, transportistas, tarifas) grounded en los datos ya
establecidos en `CONTEXT/CONTEXT.md` (el directorio real de proveedores:
UPS, FedEx, OnTrac, DHL Express USA/España, MRW, SEUR, Nacex, ReturnBear,
Logística Inversa Iberia) y en las restricciones de negocio explícitas de la
Sección 6 de `CONTEXT7.md` (SLA no prometible en picos de demanda,
devoluciones internacionales nunca automáticas, descuentos de almacenamiento
requieren aprobación de Miguel Torres).

## Estrategia de chunking

Cada documento se divide por encabezados `## ` (una sección markdown = una
unidad semántica: "SLA de entrega nacional — España", "Devoluciones
internacionales", etc.). Si una sección supera `MAX_CHUNK_CHARS`, se
subdivide en límites de **oración** (nunca a mitad de frase ni de fila de
tabla — `split_into_chunks()`), y cada pieza resultante se antepone con el
título de su sección para que el chunk quede autocontenido incluso fuera del
documento original (relevante para armar el prompt de generación en una
fase futura).

## Modelo de embeddings

`embed()` usa un cliente OpenAI-compatible (`EMBEDDING_API_BASE`,
`EMBEDDING_API_KEY`, `EMBEDDING_MODEL` en `.env`) — es el patrón estándar
para el modelo de embeddings gratuito que 4Geeks provee a sus estudiantes
(un proxy OpenAI-compatible), pero este repo no trae las credenciales reales
de ese proxy. Sin `.env` configurado, `embed()` falla explícito (no hay
fallback silencioso a un modelo distinto). `setup()` acepta un parámetro
`embed_fn` inyectable precisamente para poder probar el chunking + la
indexación en Qdrant sin depender de una llamada real a un LLM — ver
`tests/pipelines/test_rag.py` y la verificación documentada en
`Pasos/rag-knowledge-base-fase1.md`.

**Nunca reutilizar `EMBEDDING_MODEL` para generación** (Sección "Cómo
Empezar" de la guía): el modelo/endpoint de generación es una fase futura
(`retrieve`/`query`, no implementada aquí) y usará variables de entorno
separadas (`GENERATION_API_BASE`, `GENERATION_API_KEY`, `GENERATION_MODEL`).

## Idempotencia de `setup()`

Cada punto de Qdrant usa un **ID determinístico** (`UUID5` sobre
`company:source_document:chunk_index`, `_chunk_point_id()`), no un ID
aleatorio. Volver a correr `setup()` sobre los mismos documentos genera
exactamente los mismos IDs, y `client.upsert()` sobreescribe esos puntos en
vez de duplicarlos — se eligió esta estrategia (IDs determinísticos) en vez
de "borrar y recargar" porque es más barata en desarrollo iterativo (no hay
que re-indexar los 4 documentos completos si solo cambió uno) y dejaría de
funcionar de forma segura solo si cambia el *orden* de las secciones de un
documento entre corridas (caso que no ocurre en este pipeline: el orden de
`## ` en el markdown fuente es determinista). `recreate=True` sigue
disponible para el caso en que cambie la lógica de chunking en sí y los
`chunk_index` ya no correspondan a las mismas secciones que antes.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent.parent
KNOWLEDGE_BASE_DIR = ROOT_DIR / "docs" / "company-knowledge-base"

load_dotenv(PACKAGE_DIR / ".env")

COLLECTION_NAME = "trackflow_knowledge"  # nombre exacto pedido por CONTEXT7.md, Seccion "Cómo Empezar"
COMPANY = "trackflow"
LANGUAGE = "es"
MAX_CHUNK_CHARS = 900

# Filename -> identificador corto de CONTEXT7.md Seccion 3 (payload.source_document).
SOURCE_DOCUMENT_BY_FILENAME = {
    "trackflow-sla-delivery.es.md": "sla-delivery",
    "trackflow-returns-policy.es.md": "returns-policy",
    "trackflow-carrier-coverage.es.md": "carrier-coverage",
    "trackflow-storage-pricing.es.md": "storage-pricing",
}

# Namespace fijo (constante, no aleatorio) para los UUID5 deterministicos de
# _chunk_point_id() -- ver "Idempotencia de setup()" en el docstring del modulo.
_ID_NAMESPACE = uuid.UUID("d9f6a9b0-6b1a-4e7a-9c8e-5f2a6b7c8d9e")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")


@dataclass(frozen=True)
class Chunk:
    source_document: str
    section: str
    chunk_index: int
    text: str


def parse_markdown_sections(text: str) -> list[tuple[str, str]]:
    """`(titulo_de_seccion, cuerpo)` por cada encabezado `## ` del documento.

    El titulo `# ` (nivel 1, titulo del documento) no genera seccion propia.
    Secciones sin contenido (cuerpo vacio) se descartan.
    """
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_body: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_title is not None:
                sections.append((current_title, current_body))
            current_title = line[3:].strip()
            current_body = []
        elif line.startswith("# "):
            continue
        elif current_title is not None:
            current_body.append(line)

    if current_title is not None:
        sections.append((current_title, current_body))

    return [(title, "\n".join(body).strip()) for title, body in sections if "\n".join(body).strip()]


def split_into_chunks(section_text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Divide `section_text` en piezas de a lo sumo `max_chars`, cortando solo
    en limites de oracion. Si una sola "oracion" (p. ej. una fila de tabla
    markdown) ya supera `max_chars`, se mantiene entera -- una regla o fila
    de tabla cortada a la mitad es peor que un chunk un poco mas largo.
    """
    if len(section_text) <= max_chars:
        return [section_text]

    sentences = _SENTENCE_SPLIT_RE.split(section_text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_document(path: Path) -> list[Chunk]:
    source_document = SOURCE_DOCUMENT_BY_FILENAME.get(path.name)
    if source_document is None:
        raise ValueError(f"{path.name} no esta en SOURCE_DOCUMENT_BY_FILENAME -- ver CONTEXT7.md Seccion 3.")

    sections = parse_markdown_sections(path.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    chunk_index = 0
    for section_title, section_body in sections:
        for piece in split_into_chunks(section_body):
            # El titulo de seccion se antepone al texto: el chunk queda
            # autocontenido (una "unidad autocontenida", CONTEXT7.md Fase 1)
            # incluso fuera del documento original.
            chunk_text = f"{section_title}\n\n{piece}"
            chunks.append(Chunk(source_document=source_document, section=section_title, chunk_index=chunk_index, text=chunk_text))
            chunk_index += 1
    return chunks


def embed(text: str) -> list[float]:
    """Vector de `text` con el modelo de EMBEDDINGS (nunca el de generacion).

    Misma funcion para los chunks al indexar y para la pregunta del usuario
    al consultar (CONTEXT7.md, Fase 1). Requiere `EMBEDDING_API_BASE` /
    `EMBEDDING_API_KEY` en `.env` -- sin credenciales reales, falla explicito
    en vez de devolver un vector inventado.
    """
    from openai import OpenAI  # import local: setup() con embed_fn inyectado no necesita este SDK

    client = OpenAI(base_url=os.environ.get("EMBEDDING_API_BASE") or None, api_key=os.environ.get("EMBEDDING_API_KEY", ""))
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _chunk_point_id(company: str, source_document: str, chunk_index: int) -> str:
    """ID deterministico (UUID5): mismo chunk logico -> mismo ID siempre. Ver
    "Idempotencia de setup()" en el docstring del modulo."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{company}:{source_document}:{chunk_index}"))


def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int, recreate: bool = False) -> None:
    exists = client.collection_exists(collection_name)
    if recreate and exists:
        client.delete_collection(collection_name)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )


def setup(
    source_dir: Path = KNOWLEDGE_BASE_DIR,
    collection_name: str = COLLECTION_NAME,
    qdrant_client: QdrantClient | None = None,
    embed_fn: Callable[[str], list[float]] = embed,
    recreate: bool = False,
) -> int:
    """Parsea, chunkea, embebe e indexa los documentos de `source_dir` en Qdrant.

    Idempotente por IDs deterministicos (ver docstring del modulo).
    `qdrant_client`/`embed_fn` son inyectables para poder probar la funcion
    sin un Qdrant/LLM reales -- ver tests/pipelines/test_rag.py.

    Devuelve el numero de chunks indexados.
    """
    client = qdrant_client or QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))

    doc_paths = sorted(source_dir.glob("*.md"))
    if not doc_paths:
        raise FileNotFoundError(f"No hay documentos .md en {source_dir}")

    all_chunks: list[Chunk] = []
    for path in doc_paths:
        all_chunks.extend(chunk_document(path))

    if not all_chunks:
        raise ValueError(f"{source_dir} no produjo ningun chunk -- revisar el parseo de encabezados.")

    vectors = [embed_fn(chunk.text) for chunk in all_chunks]
    vector_size = len(vectors[0])

    ensure_collection(client, collection_name, vector_size, recreate=recreate)

    points = [
        PointStruct(
            id=_chunk_point_id(COMPANY, chunk.source_document, chunk.chunk_index),
            vector=vector,
            payload={
                "company": COMPANY,
                "source_document": chunk.source_document,
                "section": chunk.section,
                "language": LANGUAGE,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
            },
        )
        for chunk, vector in zip(all_chunks, vectors)
    ]

    client.upsert(collection_name=collection_name, points=points)
    return len(points)


if __name__ == "__main__":
    indexed = setup()
    print(f"Indexados {indexed} chunks en la coleccion '{COLLECTION_NAME}'.")
