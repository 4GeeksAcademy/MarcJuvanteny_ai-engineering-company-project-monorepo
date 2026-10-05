"""Backend de memoria persistente del agente (`CONTEXT/CONTEXT8.md`, Hito 8
Parte 1: "Elige un backend de memoria persistente... y documenta por escrito
por qué encaja con lo que tu agente necesita recordar").

## Por qué Redis

TrackFlow ya corre Redis en este monorepo (`services/incidents-api`, broker
de Celery -- ver `docker-compose.yml`, servicio "redis"). Lo que el agente
necesita recordar (`CONTEXT8.md`, "Qué SÍ vale la pena recordar") son hechos
estructurados y de baja cardinalidad, consolidados por `(carrier, country)`
o por cliente B2B -- reglas de asignación de carrier, contexto de
incidentes recurrentes, preferencias de reporte. Ninguno de esos casos
necesita busqueda semantica (similaridad de embeddings): se consultan por
una clave exacta y conocida (el carrier/pais de la pregunta actual, el
cliente B2B actual), no por "que tan parecido es esto a la pregunta". Una
VectorDB resolveria un problema que esta memoria no tiene, a cambio de mas
infraestructura nueva; una base clave-valor que YA esta corriendo en este
repo es la opcion mas simple que cumple el requisito.

## Por qué NUNCA en las colecciones RAG

`trackflow_knowledge` (Qdrant, `data/process/rag.py`/`data/pipelines/rag.py`)
es documentacion curada de la empresa, de solo lectura para el agente (ver
`CONTEXT7.md`). Esta memoria es el extremo opuesto: hechos episodicos,
propuestos por el propio agente, aprobados por un humano turno a turno --
mezclarlos en la misma coleccion rompe los evals de retrieval existentes
(`data/eval/evaluate_retrieval.py`, Recall@3 ya calibrado contra el corpus
curado) y abre una superficie de "poisoning" (un hecho aprobado por error
quedaria indexado junto a documentacion oficial, indistinguible para
`retrieve()`). Por eso esta memoria vive en un namespace Redis totalmente
aparte (`agent_memory:*`), nunca en Qdrant.

## Interfaz explícita de lectura/escritura

El agente NUNCA debe acumular memoria agregando texto libre al system
prompt turno a turno (`CONTEXT8.md`: "el agente no debe acumular estado
simplemente agregando todo al system prompt"). En cambio, `read_memory()`
devuelve como maximo las entradas relevantes a la clave de consolidacion de
la pregunta actual (ver `agent_graph.py`, nodo `retrieve_memory`), y
`write_memory()` es el UNICO punto de escritura, llamado solo despues de
que el usuario aprueba una propuesta explicita (`memory_proposal.py` +
`memory_decision.py`) -- nunca directamente desde la auto-evaluacion.

## Consolidación y Limpieza (checklist "Consolidación y Limpieza")

Dos mecanismos reales, no simulados, aplicados en cada `write_memory()`:

1. **Expiración (TTL nativo de Redis, `MEMORY_TTL_SECONDS`, 180 días por
   defecto)**: los hechos que esta memoria guarda -- reglas de carrier,
   contexto de incidentes, preferencias de cliente -- son correcciones
   *vigentes*, no verdades permanentes: un carrier puede volver a cambiar
   su cobertura sin que nadie se lo informe de nuevo al agente. Dejar una
   entrada vivir para siempre arriesga que el agente repita una regla ya
   obsoleta con la misma confianza que una recién confirmada. 180 días
   (~2 ciclos de reporte trimestral de TrackFlow) se eligió como un plazo
   que sobrevive una temporada operativa completa pero fuerza
   re-confirmación periódica -- cada `write_memory()` (incluida una
   re-confirmación/edición) renueva el TTL, así que una regla que se
   sigue usando y corrigiendo nunca expira por accidente.
2. **Capacidad acotada con desalojo por antigüedad
   (`MAX_MEMORY_ENTRIES`, 200 por defecto, `enforce_memory_capacity()`)**:
   TrackFlow tiene un universo acotado de carriers (8) y países (2) --
   `carrier_rule`/`incident_context` nunca van a crecer sin control -- pero
   `client_preference` es una clave por cliente B2B, potencialmente
   decenas a lo largo de los años sin un límite natural. Sin un tope, la
   memoria crecería indefinidamente contradiciendo el propio requisito del
   checklist. Cada `write_memory()` dispara `enforce_memory_capacity()`:
   si el total de entradas supera el máximo, se descartan las entradas con
   `updated_at` más antiguo -- la entrada que nadie volvió a confirmar ni
   corregir en más tiempo es la de menor relevancia disponible sin
   necesitar un modelo de relevancia real (que requeriría credenciales de
   4Geeks, igual que `classify_intent`/`evaluate_for_memory_proposal`).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")

REDIS_URL = os.environ.get("AGENT_MEMORY_REDIS_URL") or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MEMORY_KEY_PREFIX = "agent_memory:"

VALID_CATEGORIES = ("carrier_rule", "incident_context", "client_preference")

# Consolidación y Limpieza -- ver docstring del módulo para el porqué de
# cada valor.
MEMORY_TTL_SECONDS = int(os.environ.get("AGENT_MEMORY_TTL_SECONDS", str(60 * 60 * 24 * 180)))  # 180 dias
MAX_MEMORY_ENTRIES = int(os.environ.get("AGENT_MEMORY_MAX_ENTRIES", "200"))


class MemoryEntry(BaseModel):
    """Un hecho consolidado. `key` es la clave de consolidación
    (`CONTEXT8.md`, "Consolidación sugerida": por `carrier+país`, o por
    cliente B2B para preferencias de reporte) -- nunca por ticket
    individual, para que las reglas no queden fragmentadas."""

    model_config = ConfigDict(extra="forbid")

    key: str
    category: str
    fact: str
    source_thread_id: str
    created_at: str
    updated_at: str


class RedisLike(Protocol):
    def get(self, name: str) -> bytes | str | None: ...
    def set(self, name: str, value: str, ex: int | None = None) -> object: ...
    def keys(self, pattern: str) -> list[bytes | str]: ...
    def delete(self, *names: str) -> object: ...


def _default_redis_client() -> RedisLike:
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


def read_memory(key: str, *, client: RedisLike | None = None) -> MemoryEntry | None:
    """Lee la entrada consolidada para `key` (p. ej. `"SEUR:ES"` o
    `"client:glowlab-cosmetics"`). `None` si nunca se escribió nada para esa
    clave -- nunca falla ni lanza si Redis no tiene el dato, un agente sin
    memoria para este caso es un estado válido, no un error."""

    active_client = client or _default_redis_client()
    raw = active_client.get(f"{MEMORY_KEY_PREFIX}{key}")
    if raw is None:
        return None
    return MemoryEntry.model_validate(json.loads(raw))


def write_memory(
    entry: MemoryEntry,
    *,
    client: RedisLike | None = None,
    enforce_capacity: bool = True,
    max_entries: int = MAX_MEMORY_ENTRIES,
) -> None:
    """Upsert consolidado: si ya había una entrada para `entry.key`, la
    reemplaza (no la apila) -- `CONTEXT8.md` pide consolidar por
    carrier+país, no acumular una entrada por ticket. Escribe con TTL
    (`MEMORY_TTL_SECONDS`) y, salvo que se pida lo contrario, dispara
    `enforce_memory_capacity()` después -- ver "Consolidación y Limpieza"
    en el docstring del módulo."""

    active_client = client or _default_redis_client()
    active_client.set(f"{MEMORY_KEY_PREFIX}{entry.key}", entry.model_dump_json(), ex=MEMORY_TTL_SECONDS)
    if enforce_capacity:
        enforce_memory_capacity(max_entries=max_entries, client=active_client)


def delete_memory(key: str, *, client: RedisLike | None = None) -> None:
    """Checklist "Consolidación y Limpieza" -- borrado explícito de una
    entrada (p. ej. una regla de carrier que ya no aplica)."""

    active_client = client or _default_redis_client()
    active_client.delete(f"{MEMORY_KEY_PREFIX}{key}")


def list_memory_keys(*, client: RedisLike | None = None) -> list[str]:
    active_client = client or _default_redis_client()
    raw_keys = active_client.keys(f"{MEMORY_KEY_PREFIX}*")
    return [(k.decode() if isinstance(k, bytes) else k).removeprefix(MEMORY_KEY_PREFIX) for k in raw_keys]


def enforce_memory_capacity(
    *, max_entries: int = MAX_MEMORY_ENTRIES, client: RedisLike | None = None
) -> list[str]:
    """Checklist "Consolidación y Limpieza": "mecanismo de consolidación
    que evite que la memoria crezca sin control... descartar entradas de
    baja relevancia". Si el total de entradas supera `max_entries`,
    descarta las de `updated_at` más antiguo hasta volver al límite.
    Devuelve las claves descartadas (lista vacía si no hizo falta
    descartar nada) -- útil para auditar/testear qué se limpió."""

    active_client = client or _default_redis_client()
    keys = list_memory_keys(client=active_client)
    if len(keys) <= max_entries:
        return []

    entries = [entry for entry in (read_memory(key, client=active_client) for key in keys) if entry is not None]
    entries.sort(key=lambda entry: entry.updated_at)  # mas antiguo primero

    overflow = len(entries) - max_entries
    to_evict = entries[:overflow]
    for entry in to_evict:
        delete_memory(entry.key, client=active_client)

    return [entry.key for entry in to_evict]


def make_entry(key: str, category: str, fact: str, *, source_thread_id: str) -> MemoryEntry:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category debe ser una de {VALID_CATEGORIES}, recibido: {category!r}")
    now = datetime.now(timezone.utc).isoformat()
    return MemoryEntry(
        key=key, category=category, fact=fact, source_thread_id=source_thread_id, created_at=now, updated_at=now
    )
