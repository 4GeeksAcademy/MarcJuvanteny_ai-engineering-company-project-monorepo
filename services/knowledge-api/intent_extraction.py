"""Extrae argumentos estructurados de una pregunta en lenguaje natural, para
armar la llamada a una tool del MCP Server (`mcps/trackflow-mcp`).

Heurística determinista y documentada -- un stand-in de lo que idealmente
sería una extracción por LLM (`GENERATION_MODEL`), igual que
`classify_intent()` en `agent_graph.py`: sin credenciales reales de 4Geeks
en este repo no se puede probar esa versión de forma confiable y offline.

Misma lógica que `tools/incidents_tool.py::extract_incident_query` /
`tools/inventory_tool.py::extract_inventory_query` (eliminados -- ver
`Pasos/rag-knowledge-base-fase1.md`, "Migración del agente"), movida aquí
porque ahora es responsabilidad del agente (armar los argumentos de una
llamada MCP), no de una tool HTTP local que ya no existe. Devuelve dicts
planos (no modelos Pydantic): el MCP Server ya valida el shape de entrada
con su propio schema tipado (`tools/incidents_tools.py::QueryIncidentInput`/
`tools/inventory_tools.py::QueryInventoryInput`), duplicar esa validación
acá sería redundante.
"""

from __future__ import annotations

import re

_STATUS_KEYWORDS = {
    "abiertos": "open",
    "abierto": "open",
    "en progreso": "in_progress",
    "resueltos": "resolved",
    "resuelto": "resolved",
    "descartados": "discarded",
    "descartado": "discarded",
}
_TICKET_ID_RE = re.compile(r"\b(\d+)\b")
_SKU_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+){2,}\b")


def extract_incident_query(question: str) -> dict[str, int | str]:
    """Un número suelto se interpreta como `incident_id`; si no hay número,
    palabras clave de estado arman un filtro `status`; si tampoco hay eso,
    no se aplica filtro (la tool lista todos)."""

    match = _TICKET_ID_RE.search(question)
    if match:
        return {"incident_id": int(match.group(1))}

    lowered = question.lower()
    for keyword, status in _STATUS_KEYWORDS.items():
        if keyword in lowered:
            return {"status": status}

    return {}


def extract_inventory_query(question: str) -> dict[str, str]:
    """Un token con forma de SKU (`CLT-SNK-W-42-Z`) en la pregunta filtra la
    respuesta; si no hay ninguno, no se filtra (catálogo completo)."""

    match = _SKU_RE.search(question.upper())
    return {"sku": match.group(0)} if match else {}
