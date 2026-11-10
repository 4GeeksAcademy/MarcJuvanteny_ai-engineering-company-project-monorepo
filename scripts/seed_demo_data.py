"""Datos de demo realistas para el backoffice de TrackFlow.

Genera, de forma determinista (misma semilla -> mismos datos):
  * Catalogo de SKUs de varios clientes B2B ficticios en LA y ZGZ (Postgres).
  * ~90 dias de movimientos de stock: recepciones (PO / ASN / devoluciones),
    despachos con tracking por carrier y mermas. El stock nunca baja de 0.
  * Incidencias con ciclo de vida coherente con su antiguedad (TinyDB).
  * Proveedores adicionales en EE. UU. y Espana (TinyDB).

Es idempotente: si los datos ya existen no se duplican. Todo lo creado se
puede borrar con --reset (solo toca filas generadas por este script: SKUs de
su catalogo, movimientos de sus operarios, incidencias TF-INC-* y proveedores
de su lista).

Los clientes, proveedores y operarios son ficticios. Los operarios se guardan
como UUID opaco (memory-bank/techContext.md: nunca nombre ni email).

Uso (desde la raiz del repo):
  services/incidents-api/.venv/bin/python scripts/seed_demo_data.py
  services/incidents-api/.venv/bin/python scripts/seed_demo_data.py --reset
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT_DIR / "services" / "incidents-api"
sys.path.insert(0, str(SERVICE_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(SERVICE_DIR / ".env")

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import Session, SQLModel, delete, func, select  # noqa: E402
from tinydb import Query, TinyDB  # noqa: E402

from models import (  # noqa: E402
    SKU,
    IncidentResponse,
    StockEntry,
    StockExit,
    SupplierResponse,
)

SEED = 20261109
DAYS_OF_HISTORY = 90
NOW = datetime.now(timezone.utc).replace(microsecond=0)

# --------------------------------------------------------------------------
# Operarios (UUID opaco y determinista a partir de un alias interno).
# --------------------------------------------------------------------------
_NS = uuid.UUID("6f1c2a52-9a3e-4c1e-8f7e-7d1b0c7a9e11")
OPERATORS = {
    "LA": [str(uuid.uuid5(_NS, f"op-la-{i}")) for i in range(1, 6)],
    "ZGZ": [str(uuid.uuid5(_NS, f"op-zgz-{i}")) for i in range(1, 6)],
}
ALL_OPERATORS = OPERATORS["LA"] + OPERATORS["ZGZ"]

# --------------------------------------------------------------------------
# Catalogo: (cliente, categoria, prefijo, [(nombre, codigo, rotacion)])
# rotacion: unidades/dia aproximadas de salida.
# --------------------------------------------------------------------------
CATALOG = [
    ("PureStep Footwear", "fashion", [
        ("Zapatilla running Aero - Negro T41", "PST-RUN-AERO-BK-41", 3.2),
        ("Zapatilla running Aero - Negro T43", "PST-RUN-AERO-BK-43", 3.6),
        ("Zapatilla running Aero - Blanco T42", "PST-RUN-AERO-WH-42", 2.8),
        ("Bota trekking Sierra impermeable T44", "PST-TRK-SIER-44", 1.1),
        ("Sandalia Costa piel - Camel T38", "PST-SND-COST-38", 0.9),
    ]),
    ("UrbanThread", "fashion", [
        ("Sudadera oversize Basic - Gris M", "UTH-HOOD-BAS-GR-M", 4.1),
        ("Sudadera oversize Basic - Gris L", "UTH-HOOD-BAS-GR-L", 3.4),
        ("Camiseta algodon organico - Blanco S", "UTH-TEE-ORG-WH-S", 5.5),
        ("Vaquero straight Rigid - 32/32", "UTH-DNM-STR-3232", 2.2),
        ("Chaqueta cortavientos Nord - Oliva L", "UTH-JKT-NORD-OL-L", 0.7),
    ]),
    ("Kinetik Sportswear", "fashion", [
        ("Malla compresion Pro - Negro M", "KNT-TGT-PRO-BK-M", 2.6),
        ("Camiseta tecnica DryFit - Azul L", "KNT-TEE-DRY-BL-L", 3.0),
        ("Calcetin running pack 3 - T39-42", "KNT-SCK-RUN-3P-39", 6.2),
        ("Mochila hidratacion 12L", "KNT-BAG-HYD-12", 0.8),
    ]),
    ("SoundWave Electronics", "electronics", [
        ("Auriculares ANC Wave Pro", "SWE-EAR-ANC-PRO", 2.4),
        ("Altavoz bluetooth Pulse Mini", "SWE-SPK-PULSE-MINI", 1.9),
        ("Cargador GaN USB-C 65W", "SWE-CHG-GAN-65", 3.8),
        ("Cable USB-C a USB-C 2m trenzado", "SWE-CBL-CC-2M", 7.5),
        ("Barra de sonido Cinema 2.1", "SWE-SBR-CIN-21", 0.4),
    ]),
    ("Voltix Home Tech", "electronics", [
        ("Enchufe inteligente WiFi pack 2", "VTX-PLG-WIFI-2P", 2.9),
        ("Bombilla LED RGB E27 smart", "VTX-BLB-RGB-E27", 4.4),
        ("Camara seguridad interior 2K", "VTX-CAM-IND-2K", 1.2),
        ("Robot aspirador Clean S5", "VTX-VAC-CLN-S5", 0.3),
    ]),
    ("GlowLab Cosmetics", "cosmetics", [
        ("Serum vitamina C 15% 30ml", "GLB-SRM-VITC-30", 4.8),
        ("Crema hidratante acido hialuronico 50ml", "GLB-CRM-HYAL-50", 3.9),
        ("Protector solar SPF50 fluido 50ml", "GLB-SPF-50-FL", 5.1),
        ("Limpiador facial espuma 150ml", "GLB-CLN-FOAM-150", 2.7),
        ("Contorno de ojos cafeina 15ml", "GLB-EYE-CAF-15", 1.6),
    ]),
    ("Botanica Verde", "cosmetics", [
        ("Champu solido romero 75g", "BTV-SHP-ROS-75", 2.3),
        ("Aceite corporal almendra 100ml", "BTV-OIL-ALM-100", 1.4),
        ("Desodorante natural roll-on 50ml", "BTV-DEO-ROLL-50", 3.1),
    ]),
]

# Que clientes se almacenan en cada almacen (algunos en ambos).
CLIENT_WAREHOUSES = {
    "PureStep Footwear": ["LA", "ZGZ"],
    "UrbanThread": ["LA"],
    "Kinetik Sportswear": ["ZGZ"],
    "SoundWave Electronics": ["LA", "ZGZ"],
    "Voltix Home Tech": ["LA"],
    "GlowLab Cosmetics": ["ZGZ"],
    "Botanica Verde": ["ZGZ"],
}

# Carriers de despacho por almacen y formato de tracking.
CARRIERS = {
    "LA": [("ups", 0.40), ("fedex", 0.25), ("ontrac", 0.25), ("dhl", 0.10)],
    "ZGZ": [("seur", 0.40), ("mrw", 0.25), ("nacex", 0.20), ("dhl", 0.15)],
}


def tracking_number(rng: random.Random, carrier: str) -> str:
    digits = lambda n: "".join(rng.choice("0123456789") for _ in range(n))  # noqa: E731
    alnum = lambda n: "".join(rng.choice("0123456789ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(n))  # noqa: E731
    if carrier == "ups":
        return f"1Z{alnum(6)}03{digits(8)}"
    if carrier == "fedex":
        return digits(12)
    if carrier == "ontrac":
        return f"C{digits(14)}"
    if carrier == "dhl":
        return digits(10)
    if carrier == "seur":
        return f"0{digits(13)}"
    if carrier == "mrw":
        return f"0263{digits(8)}"
    return f"NX{digits(10)}"  # nacex


def weighted(rng: random.Random, options: list[tuple[str, float]]) -> str:
    return rng.choices([o for o, _ in options], weights=[w for _, w in options])[0]


def sku_code(base: str, warehouse: str) -> str:
    return base if warehouse == "LA" else f"{base}-Z"


def catalog_rows() -> list[dict[str, str | float]]:
    rows = []
    for client, category, items in CATALOG:
        for warehouse in CLIENT_WAREHOUSES[client]:
            for name, code, rotation in items:
                rows.append({
                    "name": name,
                    "sku": sku_code(code, warehouse),
                    "client_name": client,
                    "category": category,
                    "warehouse": warehouse,
                    "rotation": rotation * (0.8 if warehouse == "ZGZ" else 1.0),
                })
    return rows


# --------------------------------------------------------------------------
# Inventario
# --------------------------------------------------------------------------
def seed_inventory(engine, rng: random.Random) -> tuple[int, int, int]:
    with Session(engine) as session:
        already = session.exec(
            select(func.count()).select_from(StockEntry).where(StockEntry.user_uuid.in_(ALL_OPERATORS))
        ).one()
        if already:
            print(f"Inventario: ya hay {already} recepciones de demo, no se duplica.")
            return 0, 0, 0

        existing_codes = {s.sku for s in session.exec(select(SKU)).all()}
        skus: list[tuple[SKU, float]] = []
        for row in catalog_rows():
            if row["sku"] in existing_codes:
                continue
            rotation = float(row.pop("rotation"))
            sku = SKU(**row)
            session.add(sku)
            skus.append((sku, rotation))
        session.flush()

        po_counter = {"LA": 4100, "ZGZ": 2300}
        asn_counter = {"LA": 88000, "ZGZ": 51000}
        n_in = n_out = 0
        start = NOW - timedelta(days=DAYS_OF_HISTORY)

        for idx, (sku, rotation) in enumerate(skus):
            wh = sku.warehouse
            ops = OPERATORS[wh]
            stock = 0
            # Algunos SKUs acaban deliberadamente en stock bajo / roto.
            starving = idx % 7 == 3
            day = 0
            while day < DAYS_OF_HISTORY:
                when = start + timedelta(days=day, hours=rng.randint(6, 20), minutes=rng.randint(0, 59))
                # Reposicion: cuando baja de ~10 dias de cobertura (salvo SKUs "starving" al final).
                cover = rotation * 10
                late = day > DAYS_OF_HISTORY - 25
                if stock < cover and not (starving and late):
                    qty = max(12, int(rotation * rng.uniform(18, 30)) // 6 * 6)  # multiplos de caja de 6
                    po_counter[wh] += 1
                    asn_counter[wh] += rng.randint(3, 40)
                    ref = rng.choice([f"PO-{wh}-2026-{po_counter[wh]:05d}", f"ASN-{wh}-{asn_counter[wh]:06d}"])
                    session.add(StockEntry(sku_id=sku.id, quantity=qty, reference=ref, warehouse=wh,
                                           created_at=when, user_uuid=rng.choice(ops)))
                    stock += qty
                    n_in += 1
                # Salidas del dia: pedidos agrupados en 1-3 despachos.
                demand = rng.gauss(rotation, rotation * 0.45)
                if when.weekday() >= 5:
                    demand *= 0.35  # fin de semana con poca preparacion
                demand = max(0, int(round(demand)))
                for _ in range(rng.randint(1, 3)):
                    if demand <= 0 or stock <= 0:
                        break
                    qty = min(stock, demand, rng.randint(1, max(1, demand)))
                    carrier = weighted(rng, CARRIERS[wh])
                    out_time = when + timedelta(minutes=rng.randint(20, 240))
                    session.add(StockExit(sku_id=sku.id, quantity=qty, exit_type="dispatch",
                                          tracking_number=tracking_number(rng, carrier), warehouse=wh,
                                          created_at=out_time, user_uuid=rng.choice(ops)))
                    stock -= qty
                    demand -= qty
                    n_out += 1
                # Merma ocasional (rotura, caducidad, unidad danada en recepcion).
                if stock > 2 and rng.random() < 0.025:
                    qty = rng.randint(1, min(3, stock))
                    session.add(StockExit(sku_id=sku.id, quantity=qty, exit_type="loss", tracking_number=None,
                                          warehouse=wh, created_at=when + timedelta(hours=1),
                                          user_uuid=rng.choice(ops)))
                    stock -= qty
                    n_out += 1
                day += 1

        session.commit()
        print(f"Inventario: {len(skus)} SKUs, {n_in} recepciones, {n_out} salidas.")
        return len(skus), n_in, n_out


# --------------------------------------------------------------------------
# Incidencias
# --------------------------------------------------------------------------
INCIDENT_TEMPLATES = {
    "lost_parcel": [
        ("Paquete sin escaneo desde hace {d} dias - {carrier}",
         "El cliente {client} reporta que el envio {trk} no tiene movimiento desde la recogida en {wh_name}. "
         "Se ha abierto reclamacion con {carrier} (ref. {claim})."),
        ("Entrega marcada como realizada pero no recibida",
         "Destinatario de un pedido de {client} indica que no ha recibido el paquete {trk}. El carrier {carrier} "
         "marca entregado en buzon comunitario. Solicitada prueba de entrega con geolocalizacion."),
        ("Bulto extraviado en hub de {carrier}",
         "Pedido multi-bulto de {client}: llegaron 2 de 3 cajas. El tercer bulto ({trk}) figura en el hub de "
         "{carrier} sin salida a reparto."),
    ],
    "carrier_issue": [
        ("Recogida no realizada por {carrier} en {wh_name}",
         "{carrier} no se presento a la recogida programada de las {hour}:00. Quedan {n} bultos de {client} "
         "pendientes en muelle. Se reprograma para el siguiente turno."),
        ("Retraso generalizado en entregas {carrier}",
         "Desde el {date} las entregas de {carrier} en la zona acumulan +48h. Afecta a {n} envios activos, "
         "principalmente de {client}. Se valida desvio temporal a carrier alternativo."),
        ("Etiquetas rechazadas por API de {carrier}",
         "La integracion devuelve error de validacion de direccion en {n} etiquetas de {client}. "
         "Se generan manualmente para no perder el corte de las 17:00."),
        ("Cobro de recargo por volumen no acordado - {carrier}",
         "Factura de {carrier} incluye recargo por peso volumetrico en {n} envios de {client} que estan "
         "dentro de tarifa. Se solicita abono."),
    ],
    "inventory_discrepancy": [
        ("Descuadre en recuento ciclico - {sku}",
         "El recuento ciclico de la ubicacion {loc} en {wh_name} da {n} unidades menos que el sistema para "
         "{sku} ({client}). Pendiente revisar ultimas salidas y devoluciones."),
        ("Recepcion con unidades de mas en ASN de {client}",
         "La ASN {asn} declara {n} unidades menos de las recibidas fisicamente de {sku}. Se bloquea el "
         "excedente hasta confirmacion del cliente."),
        ("SKU ubicado en posicion incorrecta",
         "Picking no encuentra {sku} en {loc}; aparece en la ubicacion contigua. Se reubica y se revisa el "
         "historico de movimientos del turno de noche."),
    ],
}

BRANCH_INFO = {
    "la_warehouse": ("LA", "almacen de Los Angeles"),
    "la_office": ("LA", "oficina de Los Angeles"),
    "zaragoza_warehouse": ("ZGZ", "almacen de Zaragoza (PLAZA)"),
    "zaragoza_office": ("ZGZ", "oficina de Zaragoza"),
    "central": ("ZGZ", "operaciones centrales"),
}
CARRIER_NAMES = {"LA": ["UPS", "FedEx", "OnTrac", "DHL Express"], "ZGZ": ["SEUR", "MRW", "Nacex", "DHL Express"]}


def incident_status_for_age(rng: random.Random, age_days: int) -> str:
    if age_days > 30:
        return rng.choices(["resolved", "discarded", "in_progress"], weights=[78, 17, 5])[0]
    if age_days > 7:
        return rng.choices(["resolved", "in_progress", "discarded", "open"], weights=[45, 30, 10, 15])[0]
    return rng.choices(["open", "in_progress", "resolved"], weights=[55, 35, 10])[0]


def seed_incidents(db: TinyDB, rng: random.Random, count: int = 64) -> int:
    table = db.table("incidents")
    Incident = Query()
    if table.search(Incident.source_incident_id.test(lambda v: isinstance(v, str) and v.startswith("TF-INC-"))):
        print("Incidencias: ya existen incidencias de demo, no se duplican.")
        return 0

    catalog = catalog_rows()
    docs = []
    for i in range(count):
        category = rng.choices(list(INCIDENT_TEMPLATES), weights=[30, 45, 25])[0]
        branch = rng.choices(list(BRANCH_INFO), weights=[34, 8, 34, 8, 16])[0]
        wh, wh_name = BRANCH_INFO[branch]
        product = rng.choice([r for r in catalog if r["warehouse"] == wh])
        carrier = rng.choice(CARRIER_NAMES[wh])
        age = int(rng.triangular(0, DAYS_OF_HISTORY, 8))
        created = NOW - timedelta(days=age, hours=rng.randint(0, 10), minutes=rng.randint(0, 59))
        status = incident_status_for_age(rng, age)
        updated = created if status == "open" else min(NOW, created + timedelta(hours=rng.randint(2, 96)))
        title_t, desc_t = rng.choice(INCIDENT_TEMPLATES[category])
        fields = {
            "carrier": carrier, "client": product["client_name"], "sku": product["sku"], "wh_name": wh_name,
            "trk": tracking_number(rng, weighted(rng, CARRIERS[wh])), "claim": f"RC-{rng.randint(100000, 999999)}",
            "d": rng.randint(3, 9), "n": rng.randint(2, 38), "hour": rng.choice([11, 13, 16]),
            "date": (created - timedelta(days=rng.randint(1, 3))).strftime("%d/%m"),
            "loc": f"{rng.choice('ABCDEF')}-{rng.randint(1, 24):02d}-{rng.randint(1, 6)}",
            "asn": f"ASN-{wh}-{rng.randint(50000, 99999):06d}",
        }
        origin = "customer" if category == "lost_parcel" else rng.choices(
            ["internal", "branch", "customer"], weights=[50, 35, 15])[0]
        incident = IncidentResponse(
            title=title_t.format(**fields), description=desc_t.format(**fields), category=category,
            origin=origin, branch=branch, status=status,
            source_incident_id=f"TF-INC-2026-{10400 + i:05d}", created_at=created, updated_at=updated,
        )
        docs.append(incident.model_dump(mode="json"))

    docs.sort(key=lambda d: d["created_at"])
    table.insert_multiple(docs)
    print(f"Incidencias: {len(docs)} creadas.")
    return len(docs)


# --------------------------------------------------------------------------
# Proveedores (ficticios)
# --------------------------------------------------------------------------
EXTRA_SUPPLIERS = [
    {"name": "Pacific Fleet Services", "country": "USA", "categories": ["fleet_maintenance"],
     "rate_per_shipment": 0.42, "currency": "USD", "status": "active", "service_zone": "Los Angeles County",
     "contact_email": "accounts@pacificfleet-services.example", "notes": "Mantenimiento preventivo de 6 carretillas y 2 furgonetas. SLA 24h."},
    {"name": "Harbor Pallet Co.", "country": "USA", "categories": ["warehouse_supplies", "packaging_materials"],
     "rate_per_shipment": 0.95, "currency": "USD", "status": "active", "service_zone": "Southern California",
     "contact_email": "orders@harborpallet.example", "notes": "Palets EUR/GMA reacondicionados y film estirable."},
    {"name": "WestPrint Labels", "country": "USA", "categories": ["packaging_materials"],
     "rate_per_shipment": 0.08, "currency": "USD", "status": "active", "service_zone": "West Coast",
     "contact_email": "sales@westprintlabels.example", "notes": "Etiquetas termicas 4x6 y ribbons."},
    {"name": "Talleres Ebro Movil S.L.", "country": "Spain", "categories": ["fleet_maintenance"],
     "rate_per_shipment": 0.35, "currency": "EUR", "status": "active", "service_zone": "Aragon",
     "contact_email": "taller@ebromovil.example", "notes": "Revision mensual de carretillas y transpaletas electricas."},
    {"name": "Limpiezas Moncayo", "country": "Spain", "categories": ["cleaning_and_facilities"],
     "rate_per_shipment": 0.12, "currency": "EUR", "status": "active", "service_zone": "PLAZA Zaragoza",
     "contact_email": "contratos@limpiezasmoncayo.example", "notes": "Turno de noche L-V. Contrato renovado en septiembre."},
    {"name": "Cartonajes del Jalon", "country": "Spain", "categories": ["packaging_materials"],
     "rate_per_shipment": 0.27, "currency": "EUR", "status": "active", "service_zone": "Aragon + Navarra",
     "contact_email": "pedidos@cartonajesjalon.example", "notes": "Caja americana doble canal. Plazo 72h."},
    {"name": "Andes Mensajeria Urgente", "country": "Spain", "categories": ["carrier_last_mile"],
     "rate_per_shipment": 4.65, "currency": "EUR", "status": "suspended", "service_zone": "Peninsula",
     "contact_email": "comercial@andesmensajeria.example", "notes": "Suspendido tras 3 semanas con >8% de entregas fallidas."},
    {"name": "Stackline WMS Integrations", "country": "USA", "categories": ["it_and_wms_software"],
     "rate_per_shipment": 0.05, "currency": "USD", "status": "active", "service_zone": "Remote",
     "contact_email": "support@stackline-wms.example", "notes": "Conectores EDI con clientes B2B. Soporte 8x5 PT."},
]


def seed_suppliers(db: TinyDB) -> int:
    table = db.table("suppliers")
    existing = {s["name"] for s in table.all()}
    docs = [SupplierResponse(**s).model_dump(mode="json") for s in EXTRA_SUPPLIERS if s["name"] not in existing]
    if docs:
        table.insert_multiple(docs)
    print(f"Proveedores: {len(docs)} anadidos.")
    return len(docs)


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------
def reset(engine, db: TinyDB) -> None:
    codes = [r["sku"] for r in catalog_rows()]
    with Session(engine) as session:
        n_in = session.exec(delete(StockEntry).where(StockEntry.user_uuid.in_(ALL_OPERATORS))).rowcount
        n_out = session.exec(delete(StockExit).where(StockExit.user_uuid.in_(ALL_OPERATORS))).rowcount
        # Solo borra SKUs del catalogo de demo que ya no tengan movimientos de nadie.
        removable = []
        for sku in session.exec(select(SKU).where(SKU.sku.in_(codes))).all():
            used = session.exec(select(func.count()).select_from(StockEntry).where(StockEntry.sku_id == sku.id)).one() \
                + session.exec(select(func.count()).select_from(StockExit).where(StockExit.sku_id == sku.id)).one()
            if not used:
                removable.append(sku)
        for sku in removable:
            session.delete(sku)
        session.commit()
    Incident = Query()
    n_inc = len(db.table("incidents").remove(
        Incident.source_incident_id.test(lambda v: isinstance(v, str) and v.startswith("TF-INC-"))))
    names = {s["name"] for s in EXTRA_SUPPLIERS}
    n_sup = len(db.table("suppliers").remove(Query().name.one_of(list(names))))
    print(f"Reset: {n_in} recepciones, {n_out} salidas, {len(removable)} SKUs, {n_inc} incidencias, {n_sup} proveedores.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="Borra solo los datos generados por este script.")
    args = parser.parse_args()

    database_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    tinydb_path = os.environ.get("TINYDB_PATH")
    if not database_url or not tinydb_path:
        sys.exit("Faltan SUPABASE_DATABASE_URL / TINYDB_PATH en services/incidents-api/.env")

    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine, tables=[SKU.__table__, StockEntry.__table__, StockExit.__table__])

    with TinyDB(tinydb_path) as db:
        if args.reset:
            reset(engine, db)
            return
        rng = random.Random(SEED)
        seed_inventory(engine, rng)
        seed_incidents(db, rng)
        seed_suppliers(db)


if __name__ == "__main__":
    main()
