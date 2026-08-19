from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator, model_validator
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField, SQLModel

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

# Only 3 of the 9 Hito 10 incident categories are confirmed in memory-bank/progress.md.
# Extend this list once the remaining 6 are defined in the real Hito 10 CONTEXT.
VALID_INCIDENT_CATEGORIES = [
    "lost_parcel",
    "carrier_issue",
    "inventory_discrepancy",
]

VALID_BRANCHES = [
    "la_warehouse",
    "la_office",
    "zaragoza_warehouse",
    "zaragoza_office",
    "central",
]


class SKU(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    name: str
    sku: str = SQLField(index=True)
    client_name: str
    category: str
    warehouse: str


class StockEntry(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    sku_id: int = SQLField(foreign_key="sku.id", index=True)
    quantity: int
    reference: str
    warehouse: str
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    user_uuid: str


class StockExit(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    sku_id: int = SQLField(foreign_key="sku.id", index=True)
    quantity: int
    exit_type: str
    tracking_number: str | None = None
    warehouse: str
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    user_uuid: str


class TelemetryEventRecord(SQLModel, table=True):
    """Immutable telemetry event log. One row per TelemetryEvent received on /telemetry/events.

    No update/delete path exists for this table anywhere in the API — telemetry
    events are append-only, matching event-shcemas.json's contract guarantee
    that a recorded event is never mutated after ingestion.
    """

    __tablename__ = "telemetry_events"
    __table_args__ = (
        Index("ix_telemetry_events_properties_gin", "properties", postgresql_using="gin"),
    )

    event_id: str = SQLField(primary_key=True)
    timestamp: datetime = SQLField(index=True)
    session_id: str
    user_id: str
    event_type: str = SQLField(index=True)
    schema_version: str
    request_id: str
    properties: dict[str, Any] = SQLField(sa_column=Column(JSONB, nullable=False))


class SupplierStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class IncidentStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISCARDED = "discarded"


class IncidentOrigin(StrEnum):
    CUSTOMER = "customer"
    BRANCH = "branch"
    INTERNAL = "internal"


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


VALID_STATUSES = [status.value for status in SupplierStatus]
VALID_INCIDENT_STATUSES = [status.value for status in IncidentStatus]
VALID_INCIDENT_ORIGINS = [origin.value for origin in IncidentOrigin]

INCIDENT_STATUS_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.IN_PROGRESS, IncidentStatus.DISCARDED},
    IncidentStatus.IN_PROGRESS: {IncidentStatus.RESOLVED, IncidentStatus.DISCARDED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.DISCARDED: set(),
}


def is_valid_incident_status_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    return target in INCIDENT_STATUS_TRANSITIONS[current]


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


class IncidentBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    valid_categories: ClassVar[set[str]] = set(VALID_INCIDENT_CATEGORIES)
    valid_branches: ClassVar[set[str]] = set(VALID_BRANCHES)

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str
    origin: IncidentOrigin
    branch: str

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in cls.valid_categories:
            raise ValueError(f"category must be one of: {sorted(cls.valid_categories)}")
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        if value not in cls.valid_branches:
            raise ValueError(f"branch must be one of: {sorted(cls.valid_branches)}")
        return value


class IncidentCreate(IncidentBase):
    pass


class IncidentResponse(IncidentBase):
    status: IncidentStatus = IncidentStatus.OPEN
    source_incident_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncidentRecord(IncidentResponse):
    id: int = Field(gt=0)


class IncidentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus


class IncidentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_status: dict[str, int]
    by_category: dict[str, int]
    by_origin: dict[str, int]
    by_branch: dict[str, int]


Incident = IncidentRecord


class UserBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    email: str = Field(min_length=5)
    hashed_password: str = Field(min_length=20)
    is_active: bool = True
    role: UserRole = UserRole.USER

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part:
            raise ValueError("email must be a valid address")
        return normalized


class UserCreate(UserBase):
    pass


class UserRegister(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    email: str = Field(min_length=5)
    password: str = Field(min_length=8)
    role: UserRole = UserRole.USER
    is_active: bool = True
    name: str | None = Field(default=None, min_length=1)
    phone: str | None = Field(default=None, min_length=3)
    address: str | None = Field(default=None, min_length=3)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part:
            raise ValueError("email must be a valid address")
        return normalized


class UserCredentialsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    email: str | None = Field(default=None, min_length=5)
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None
    role: UserRole | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part:
            raise ValueError("email must be a valid address")
        return normalized


class UserResponse(UserBase):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserRecord(UserResponse):
    id: int = Field(gt=0)


class ProfileBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    user_id: int = Field(gt=0)
    name: str | None = Field(default=None, min_length=1)
    phone: str | None = Field(default=None, min_length=3)
    address: str | None = Field(default=None, min_length=3)


class ProfileResponse(ProfileBase):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProfileRecord(ProfileResponse):
    id: int = Field(gt=0)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    name: str | None = Field(default=None, min_length=1)
    phone: str | None = Field(default=None, min_length=3)
    address: str | None = Field(default=None, min_length=3)


class UserWithProfileRecord(UserRecord):
    profile: ProfileRecord | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    email: str = Field(min_length=5)
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part:
            raise ValueError("email must be a valid address")
        return normalized


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(gt=0)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    email: str = Field(min_length=5)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part:
            raise ValueError("email must be a valid address")
        return normalized


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=8)


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


class AuthMeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    phone: str | None = None
    address: str | None = None


class AuthMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    role: UserRole
    profile: AuthMeProfile | None = None


User = UserRecord