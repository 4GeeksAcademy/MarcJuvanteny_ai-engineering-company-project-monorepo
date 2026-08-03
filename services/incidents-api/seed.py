from __future__ import annotations

import os
import sys
from pathlib import Path

from tinydb import Query, TinyDB

from models import SupplierCreate, SupplierResponse

SUPPLIERS_SEED = [
    {
        "name": "UPS Ground",
        "country": "USA",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 7.45,
        "currency": "USD",
        "status": "active",
        "service_zone": "West Coast",
        "contact_email": "business@ups.com",
        "notes": "Carrier principal para entregas locales en Los Angeles y alrededores.",
    },
    {
        "name": "FedEx Ground",
        "country": "USA",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 7.90,
        "currency": "USD",
        "status": "active",
        "service_zone": "Continental USA",
        "contact_email": "business.solutions@fedex.com",
    },
    {
        "name": "DHL Express USA",
        "country": "USA",
        "categories": ["carrier_last_mile", "carrier_international"],
        "rate_per_shipment": 14.20,
        "currency": "USD",
        "status": "active",
        "service_zone": "Continental USA + International",
        "contact_email": "business.us@dhl.com",
        "notes": "Usado para envios urgentes y exportaciones a Europa.",
    },
    {
        "name": "OnTrac",
        "country": "USA",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 6.10,
        "currency": "USD",
        "status": "active",
        "service_zone": "West Coast",
        "contact_email": "solutions@ontrac.com",
        "notes": "Carrier regional. Mejor tarifa en la zona de Los Angeles.",
    },
    {
        "name": "Laser Ship",
        "country": "USA",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 5.80,
        "currency": "USD",
        "status": "suspended",
        "service_zone": "East Coast",
        "contact_email": "business@lasership.com",
        "notes": "Suspendido. Tasa de incidencias superior al 8% en Q3.",
    },
    {
        "name": "PackSource LA",
        "country": "USA",
        "categories": ["packaging_materials"],
        "rate_per_shipment": 0.42,
        "currency": "USD",
        "status": "active",
        "contact_email": "orders@packsource.com",
        "notes": "Cajas, relleno y precinto para el almacen de Los Angeles.",
    },
    {
        "name": "CleanTeam West",
        "country": "USA",
        "categories": ["cleaning_and_facilities"],
        "rate_per_shipment": 1800.0,
        "currency": "USD",
        "status": "active",
        "contact_email": "accounts@cleanteamwest.com",
        "notes": "Tarifa mensual por servicio de limpieza del almacen de LA.",
    },
    {
        "name": "MRW Espana",
        "country": "Spain",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 4.90,
        "currency": "EUR",
        "status": "active",
        "service_zone": "Peninsula Iberica",
        "contact_email": "clientes.empresa@mrw.es",
        "notes": "Carrier principal para entregas en Espana. Contrato negociado por volumen.",
    },
    {
        "name": "SEUR",
        "country": "Spain",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 5.20,
        "currency": "EUR",
        "status": "active",
        "service_zone": "Peninsula Iberica + Baleares",
        "contact_email": "grandes.cuentas@seur.com",
    },
    {
        "name": "DHL Express Espana",
        "country": "Spain",
        "categories": ["carrier_last_mile", "carrier_international"],
        "rate_per_shipment": 12.80,
        "currency": "EUR",
        "status": "active",
        "service_zone": "Espana + Internacional",
        "contact_email": "business.es@dhl.com",
        "notes": "Envios urgentes y exportaciones desde Zaragoza.",
    },
    {
        "name": "Nacex",
        "country": "Spain",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 4.60,
        "currency": "EUR",
        "status": "active",
        "service_zone": "Aragon y zona norte",
        "contact_email": "empresas@nacex.es",
        "notes": "Carrier regional con buena cobertura en Aragon.",
    },
    {
        "name": "Logistica Inversa Iberia",
        "country": "Spain",
        "categories": ["reverse_logistics"],
        "rate_per_shipment": 6.30,
        "currency": "EUR",
        "status": "active",
        "contact_email": "operaciones@liiberia.es",
        "notes": "Gestion de devoluciones para el almacen de Zaragoza.",
    },
    {
        "name": "Embalajes Zaragoza S.L.",
        "country": "Spain",
        "categories": ["packaging_materials"],
        "rate_per_shipment": 0.28,
        "currency": "EUR",
        "status": "active",
        "contact_email": "pedidos@embalajeszgz.es",
    },
    {
        "name": "SAP WM Cloud",
        "country": "USA",
        "categories": ["it_and_wms_software"],
        "rate_per_shipment": 2200.0,
        "currency": "USD",
        "status": "suspended",
        "contact_email": "enterprise@sap.com",
        "notes": "Suspendido. Andres esta evaluando alternativas mas ligeras para el almacen de LA.",
    },
    {
        "name": "ReturnBear",
        "country": "USA",
        "categories": ["reverse_logistics"],
        "rate_per_shipment": 4.15,
        "currency": "USD",
        "status": "active",
        "service_zone": "West Coast",
        "contact_email": "partnerships@returnbear.com",
        "notes": "Gestion de devoluciones para clientes de Los Angeles.",
    },
]

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "suppliers.json"


def build_seed_documents() -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for payload in SUPPLIERS_SEED:
        validated_input = SupplierCreate(**payload)
        validated_output = SupplierResponse(**validated_input.model_dump())
        documents.append(validated_output.model_dump(mode="json"))
    return documents


def seed_suppliers(db_path: Path) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with TinyDB(db_path) as db:
        suppliers_table = db.table("suppliers")
        documents = build_seed_documents()
        supplier_query = Query()
        inserted_count = 0

        for document in documents:
            already_exists = suppliers_table.contains(
                (supplier_query.name == document["name"])
                & (supplier_query.country == document["country"])
            )
            if already_exists:
                continue

            suppliers_table.insert(document)
            inserted_count += 1

        return inserted_count


def main() -> None:
    raw_path = os.environ.get("TINYDB_PATH")
    db_path = Path(raw_path) if raw_path else DEFAULT_DB_PATH

    try:
        inserted_count = seed_suppliers(db_path)
    except OSError as exc:
        print(f"Could not write to the suppliers database at {db_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Seeded {inserted_count} suppliers into {db_path}")


if __name__ == "__main__":
    main()