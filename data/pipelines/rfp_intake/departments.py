"""Departamentos que participan en una propuesta (`CONTEXT/CONTEXT9.md`,
Sección 2.1) -- identificadores y responsables EXACTOS del BRIEFING, no
nombres genéricos."""

from __future__ import annotations

from typing import NamedTuple


class Department(NamedTuple):
    department_id: str
    name: str
    responsible: str


DEPARTMENTS: dict[str, Department] = {
    "warehouse": Department("warehouse", "Warehouse Operations", "Ana Whitfield"),
    "lastmile": Department("lastmile", "Last Mile and Carrier Management", "Carlos Vega"),
    "reverse": Department("reverse", "Reverse Logistics", "Sofía Ramos"),
}
