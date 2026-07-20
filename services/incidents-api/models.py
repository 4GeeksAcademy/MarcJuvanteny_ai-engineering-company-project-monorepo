from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator, model_validator

VALID_CATEGORIES = [
    "carrier_last_mile",
    "carrier_international",
    "warehouse_supplies",
    "packaging_materials",
    "reverse_logistics",
    "fleet_maintenance",
    "it_and_wms_software",
    "cleaning_and_facilities",
]

VALID_COUNTRIES = ["USA", "Spain"]
COUNTRY_CURRENCY_MAP = {"USA": "USD", "Spain": "EUR"}


class SupplierStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


VALID_STATUSES = [status.value for status in SupplierStatus]


class SupplierBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    valid_categories: ClassVar[set[str]] = set(VALID_CATEGORIES)
    valid_countries: ClassVar[set[str]] = set(VALID_COUNTRIES)

    name: str = Field(min_length=1)
    country: str
    categories: list[str] = Field(min_length=1)
    rate_per_shipment: PositiveFloat
    currency: str
    status: SupplierStatus
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        if value not in cls.valid_countries:
            raise ValueError(f"country must be one of: {sorted(cls.valid_countries)}")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        allowed_currencies = sorted(set(COUNTRY_CURRENCY_MAP.values()))
        if value not in allowed_currencies:
            raise ValueError(f"currency must be one of: {allowed_currencies}")
        return value

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: list[str]) -> list[str]:
        invalid_categories = sorted({category for category in value if category not in cls.valid_categories})
        if invalid_categories:
            raise ValueError(
                f"categories contains unsupported values: {invalid_categories}. Allowed values: {sorted(cls.valid_categories)}"
            )
        return value

    @model_validator(mode="after")
    def validate_country_currency_pair(self) -> SupplierBase:
        expected_currency = COUNTRY_CURRENCY_MAP[self.country]
        if self.currency != expected_currency:
            raise ValueError(
                f"currency must be {expected_currency} when country is {self.country}"
            )
        return self


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SupplierRecord(SupplierResponse):
    id: int = Field(gt=0)


class SupplierRateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rate_per_shipment: PositiveFloat


class SupplierStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SupplierStatus


Supplier = SupplierRecord