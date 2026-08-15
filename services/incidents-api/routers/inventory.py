from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select
from sqlalchemy import func

from auth_service import get_user_from_token
from database import get_db
from database import get_tinydb_path
from models import SKU, StockEntry, StockExit, UserWithProfileRecord
from schemas import (
    SKUCreate,
    SKUResponse,
    SKUSummary,
    StockEntryCreate,
    StockEntryResponse,
    StockExitCreate,
    StockExitResponse,
    StockMovementResponse,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])
bearer_scheme = HTTPBearer(auto_error=False)

SEED_SKUS = [
    {
        "name": "Zapatilla blanca clasica - Talla 42",
        "sku": "CLT-SNK-W-42",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "Zapatilla blanca clasica - Talla 42",
        "sku": "CLT-SNK-W-42-Z",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "ZGZ",
    },
    {
        "name": "Auriculares inalambricos Pro",
        "sku": "TEC-EAR-001",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "LA",
    },
    {
        "name": "Serum facial hidratante 30ml",
        "sku": "CSM-SRM-030",
        "client_name": "GlowLab Cosmetics",
        "category": "cosmetics",
        "warehouse": "ZGZ",
    },
    {
        "name": "Chino slim fit - marino 32/32",
        "sku": "CLT-CHN-N-32",
        "client_name": "UrbanThread",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "Cargador rapido USB-C 65W",
        "sku": "TEC-CHG-065",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "ZGZ",
    },
]

SEED_INBOUND = [
    {"sku": "CLT-SNK-W-42", "quantity": 30, "reference": "PO-2024-0098", "warehouse": "LA", "user_uuid": "seed-user-la-1"},
    {"sku": "CLT-SNK-W-42", "quantity": 12, "reference": "GR-LA-0234", "warehouse": "LA", "user_uuid": "seed-user-la-2"},
    {"sku": "TEC-CHG-065", "quantity": 20, "reference": "PO-2024-0112", "warehouse": "ZGZ", "user_uuid": "seed-user-zgz-1"},
    {"sku": "CSM-SRM-030", "quantity": 18, "reference": "GR-ZGZ-0041", "warehouse": "ZGZ", "user_uuid": "seed-user-zgz-2"},
]

SEED_OUTBOUND = [
    {
        "sku": "CLT-SNK-W-42",
        "quantity": 7,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10123456784",
        "warehouse": "LA",
        "user_uuid": "seed-coord-la-1",
    },
    {
        "sku": "TEC-CHG-065",
        "quantity": 2,
        "exit_type": "loss",
        "tracking_number": None,
        "warehouse": "ZGZ",
        "user_uuid": "seed-coord-zgz-1",
    },
    {
        "sku": "CSM-SRM-030",
        "quantity": 5,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10123456785",
        "warehouse": "ZGZ",
        "user_uuid": "seed-coord-zgz-2",
    },
]


def _compute_current_stock(session: Session, sku_id: int, warehouse: str) -> int:
    entries = session.exec(
        select(func.coalesce(func.sum(StockEntry.quantity), 0)).where(
            StockEntry.sku_id == sku_id,
            StockEntry.warehouse == warehouse,
        )
    ).one()
    exits = session.exec(
        select(func.coalesce(func.sum(StockExit.quantity), 0)).where(
            StockExit.sku_id == sku_id,
            StockExit.warehouse == warehouse,
        )
    ).one()
    return int(entries or 0) - int(exits or 0)


def _build_sku_response(session: Session, sku: SKU) -> SKUResponse:
    return SKUResponse(
        id=sku.id,
        name=sku.name,
        sku=sku.sku,
        client_name=sku.client_name,
        category=sku.category,
        warehouse=sku.warehouse,
        current_stock=_compute_current_stock(session, sku.id, sku.warehouse),
    )


def _build_sku_summary(sku: SKU) -> SKUSummary:
    return SKUSummary(
        id=sku.id,
        sku=sku.sku,
        name=sku.name,
        warehouse=sku.warehouse,
    )


def _get_sku_or_404(session: Session, sku_id: int) -> SKU:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found.")
    return sku


def get_current_inventory_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserWithProfileRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_user_from_token(get_tinydb_path(), credentials.credentials)


def seed_inventory_if_empty(session: Session) -> None:
    has_data = session.exec(select(SKU.id).limit(1)).first()
    if has_data is not None:
        return

    created_by_sku_code: dict[str, SKU] = {}
    for payload in SEED_SKUS:
        sku = SKU(**payload)
        session.add(sku)
        session.flush()
        created_by_sku_code[sku.sku] = sku

    now = datetime.now(timezone.utc)
    for payload in SEED_INBOUND:
        source_sku = created_by_sku_code[payload["sku"]]
        session.add(
            StockEntry(
                sku_id=source_sku.id,
                quantity=payload["quantity"],
                reference=payload["reference"],
                warehouse=payload["warehouse"],
                created_at=now,
                user_uuid=payload["user_uuid"],
            )
        )

    for payload in SEED_OUTBOUND:
        source_sku = created_by_sku_code[payload["sku"]]
        session.add(
            StockExit(
                sku_id=source_sku.id,
                quantity=payload["quantity"],
                exit_type=payload["exit_type"],
                tracking_number=payload["tracking_number"],
                warehouse=payload["warehouse"],
                created_at=now,
                user_uuid=payload["user_uuid"],
            )
        )

    session.commit()


@router.get("/products", response_model=list[SKUResponse])
def list_products(db: Session = Depends(get_db)) -> list[SKUResponse]:
    skus = db.exec(select(SKU).order_by(SKU.id)).all()
    return [_build_sku_response(db, sku) for sku in skus]


@router.post("/products", response_model=SKUResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: SKUCreate,
    db: Session = Depends(get_db),
    current_user: UserWithProfileRecord = Depends(get_current_inventory_user),
) -> SKUResponse:
    _ = current_user
    duplicated = db.exec(select(SKU).where(SKU.sku == payload.sku, SKU.warehouse == payload.warehouse)).first()
    if duplicated is not None:
        raise HTTPException(status_code=409, detail="A SKU with the same code already exists in this warehouse.")

    sku = SKU(**payload.model_dump())
    db.add(sku)
    db.commit()
    db.refresh(sku)
    return _build_sku_response(db, sku)


@router.get("/products/{id}", response_model=SKUResponse)
def get_product(id: int, db: Session = Depends(get_db)) -> SKUResponse:
    sku = _get_sku_or_404(db, id)
    return _build_sku_response(db, sku)


@router.post("/orders/inbound", response_model=StockEntryResponse, status_code=status.HTTP_201_CREATED)
def create_inbound_order(
    payload: StockEntryCreate,
    db: Session = Depends(get_db),
    current_user: UserWithProfileRecord = Depends(get_current_inventory_user),
) -> StockEntryResponse:
    sku = _get_sku_or_404(db, payload.sku_id)
    if sku.warehouse != payload.warehouse:
        raise HTTPException(status_code=400, detail="warehouse does not match the SKU warehouse.")

    entry = StockEntry(**payload.model_dump(), user_uuid=str(current_user.id))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return StockEntryResponse(
        id=entry.id,
        sku=_build_sku_summary(sku),
        quantity=entry.quantity,
        reference=entry.reference,
        warehouse=entry.warehouse,
        created_at=entry.created_at,
    )


@router.post("/orders/outbound", response_model=StockExitResponse, status_code=status.HTTP_201_CREATED)
def create_outbound_order(
    payload: StockExitCreate,
    db: Session = Depends(get_db),
    current_user: UserWithProfileRecord = Depends(get_current_inventory_user),
) -> StockExitResponse:
    sku = _get_sku_or_404(db, payload.sku_id)
    if sku.warehouse != payload.warehouse:
        raise HTTPException(status_code=400, detail="warehouse does not match the SKU warehouse.")

    available_stock = _compute_current_stock(db, sku.id, sku.warehouse)
    if payload.quantity > available_stock:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock for SKU '{sku.sku}'. Available: {available_stock}, requested: {payload.quantity}.",
        )

    movement = StockExit(**payload.model_dump(), user_uuid=str(current_user.id))
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return StockExitResponse(
        id=movement.id,
        sku=_build_sku_summary(sku),
        quantity=movement.quantity,
        exit_type=movement.exit_type,
        tracking_number=movement.tracking_number,
        warehouse=movement.warehouse,
        created_at=movement.created_at,
    )


@router.get("/orders", response_model=list[StockMovementResponse])
def list_orders(db: Session = Depends(get_db)) -> list[StockMovementResponse]:
    sku_map = {item.id: item for item in db.exec(select(SKU)).all()}

    inbound_rows = db.exec(select(StockEntry).order_by(StockEntry.created_at.desc())).all()
    outbound_rows = db.exec(select(StockExit).order_by(StockExit.created_at.desc())).all()

    items: list[StockMovementResponse] = []

    for row in inbound_rows:
        sku = sku_map.get(row.sku_id)
        if sku is None:
            continue
        items.append(
            StockMovementResponse(
                movement_type="inbound",
                id=row.id,
                sku=_build_sku_summary(sku),
                warehouse=row.warehouse,
                quantity=row.quantity,
                created_at=row.created_at,
                reference=row.reference,
            )
        )

    for row in outbound_rows:
        sku = sku_map.get(row.sku_id)
        if sku is None:
            continue
        items.append(
            StockMovementResponse(
                movement_type="outbound",
                id=row.id,
                sku=_build_sku_summary(sku),
                warehouse=row.warehouse,
                quantity=row.quantity,
                created_at=row.created_at,
                exit_type=row.exit_type,
                tracking_number=row.tracking_number,
            )
        )

    items.sort(key=lambda item: item.created_at, reverse=True)
    return items
