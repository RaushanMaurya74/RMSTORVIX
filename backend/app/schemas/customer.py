"""Pydantic schemas for Customer CRUD, pagination, and GSTIN verification."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import OptionalCleanText, OptionalEmail


class CustomerBase(BaseModel):
    """Shared customer fields with input normalization."""

    name: str = Field(min_length=2, max_length=160)
    company_name: OptionalCleanText = Field(default=None, max_length=180)
    email: OptionalEmail = None
    phone: OptionalCleanText = Field(default=None, max_length=40)
    tax_id: OptionalCleanText = Field(default=None, max_length=64)
    gstin_verified: bool = Field(default=False)
    address_line1: OptionalCleanText = Field(default=None, max_length=200)
    address_line2: OptionalCleanText = Field(default=None, max_length=200)
    city: OptionalCleanText = Field(default=None, max_length=100)
    state: OptionalCleanText = Field(default=None, max_length=100)
    postal_code: OptionalCleanText = Field(default=None, max_length=30)
    country: OptionalCleanText = Field(default=None, max_length=100)
    notes: OptionalCleanText = Field(default=None, max_length=2000)
    is_active: bool = Field(default=True)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Customer name must contain at least 2 characters.")
        return cleaned

    @field_validator("tax_id")
    @classmethod
    def normalize_tax_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    @model_validator(mode="after")
    def validate_verified_gstin(self) -> "CustomerBase":
        if self.gstin_verified:
            if not self.tax_id:
                raise ValueError("GSTIN is required when marking GSTIN as verified.")
            from app.services.gstin_service import verify_gstin_checksum

            if not verify_gstin_checksum(self.tax_id):
                raise ValueError("Provided GSTIN failed format or checksum verification.")
        return self


class CustomerCreate(CustomerBase):
    """Payload to create a customer."""


class CustomerUpdate(CustomerBase):
    """Payload to update an existing customer."""


class CustomerResponse(BaseModel):
    """Serialized customer record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    name: str
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    tax_id: str | None = None
    gstin_verified: bool = False
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    """Paginated list of customers."""

    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class GstinVerifyRequest(BaseModel):
    """Payload to verify a 15-character Indian GSTIN."""

    gstin: str = Field(min_length=1, max_length=32)

    @field_validator("gstin")
    @classmethod
    def normalize_gstin(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Enter a GSTIN to verify.")
        return cleaned


class GstinVerifyResponse(BaseModel):
    """Structured GSTIN verification and auto-fill payload."""

    gstin: str
    valid: bool
    checksum_valid: bool
    state_code: str | None = None
    state: str | None = None
    country: str | None = None
    pan: str | None = None
    company_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postal_code: str | None = None
    lookup_source: Literal["offline_checksum", "external_api"]
    message: str
