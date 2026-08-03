from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

VALID_INVENTORY_CATEGORIES = {"fashion", "electronics", "cosmetics"}
VALID_WAREHOUSES = {"LA", "ZGZ"}
VALID_EXIT_TYPES = {"dispatch", "loss"}


class SKUCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    category: str
    warehouse: str

    @model_validator(mode="after")
    def validate_values(self) -> "SKUCreate":
        if self.category not in VALID_INVENTORY_CATEGORIES:
            raise ValueError("category must be one of: ['cosmetics', 'electronics', 'fashion']")
        if self.warehouse not in VALID_WAREHOUSES:
            raise ValueError("warehouse must be one of: ['LA', 'ZGZ']")
        return self


class SKUResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    sku: str
    client_name: str
    category: str
    warehouse: str
    current_stock: int


class StockEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    reference: str = Field(min_length=1)
    warehouse: str

    @model_validator(mode="after")
    def validate_values(self) -> "StockEntryCreate":
        if self.warehouse not in VALID_WAREHOUSES:
            raise ValueError("warehouse must be one of: ['LA', 'ZGZ']")
        return self


class StockEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    sku_id: int
    quantity: int
    reference: str
    warehouse: str
    created_at: datetime
    user_uuid: str


class StockExitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    exit_type: str
    tracking_number: str | None = None
    warehouse: str

    @model_validator(mode="after")
    def validate_values(self) -> "StockExitCreate":
        if self.warehouse not in VALID_WAREHOUSES:
            raise ValueError("warehouse must be one of: ['LA', 'ZGZ']")

        if self.exit_type not in VALID_EXIT_TYPES:
            raise ValueError("exit_type must be one of: ['dispatch', 'loss']")

        if self.exit_type == "dispatch" and not self.tracking_number:
            raise ValueError("tracking_number is required when exit_type is 'dispatch'.")

        if self.exit_type == "loss" and self.tracking_number is not None:
            raise ValueError("tracking_number must be null when exit_type is 'loss'.")

        return self


class StockExitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    sku_id: int
    quantity: int
    exit_type: str
    tracking_number: str | None = None
    warehouse: str
    created_at: datetime
    user_uuid: str


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movement_type: str
    id: int
    sku_id: int
    sku: str
    sku_name: str
    warehouse: str
    quantity: int
    created_at: datetime
    user_uuid: str
    reference: str | None = None
    exit_type: str | None = None
    tracking_number: str | None = None
