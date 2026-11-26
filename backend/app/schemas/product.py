"""Pydantic schemas for Product / Service catalog CRUD, HSN code, pricing, and stock."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.schemas.common import OptionalCleanText, OptionalHsnCode


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ProductBase(BaseModel):
    """Shared product/service fields with HSN code and exact decimal validation."""

    name: str = Field(min_length=2, max_length=160)
    sku: OptionalCleanText = Field(default=None, max_length=64)
    hsn_code: OptionalHsnCode = None
    description: OptionalCleanText = Field(default=None, max_length=2000)
    unit: OptionalCleanText = Field(default=None, max_length=32)
    purchase_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        le=Decimal("999999999.99"),
    )
    unit_price: Decimal = Field(ge=Decimal("0.00"), le=Decimal("999999999.99"))
    tax_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
    )
    tax_label: OptionalCleanText = Field(default=None, max_length=40)
    stock_quantity: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("999999999.99"),
    )
    is_active: bool = Field(default=True)

    @model_validator(mode="before")
    @classmethod
    def accept_selling_price_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "unit_price" not in data and "selling_price" in data:
            copied = dict(data)
            copied["unit_price"] = copied.pop("selling_price")
            return copied
        return data

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Item name must contain at least 2 characters.")
        return cleaned

    @field_validator("unit_price", "tax_rate", "stock_quantity")
    @classmethod
    def normalize_decimal(cls, value: Decimal) -> Decimal:
        return _quantize_money(value)

    @field_validator("purchase_price")
    @classmethod
    def normalize_optional_decimal(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _quantize_money(value)


class ProductCreate(ProductBase):
    """Payload to create a product or service."""


class ProductUpdate(ProductBase):
    """Payload to update an existing product or service."""


class ProductResponse(BaseModel):
    """Serialized product or service record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    name: str
    sku: str | None = None
    hsn_code: str | None = None
    description: str | None = None
    unit: str | None = None
    purchase_price: Decimal | None = None
    unit_price: Decimal
    tax_rate: Decimal
    tax_label: str | None = None
    stock_quantity: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def selling_price(self) -> Decimal:
        """Explicit selling price alias matching unit_price."""
        return self.unit_price


class ProductStockAdjustRequest(BaseModel):
    """Payload to record an inventory purchase (+delta) or write-off/adjustment (-delta)."""

    delta_quantity: Decimal
    reason: OptionalCleanText = Field(default=None, max_length=255)

    @field_validator("delta_quantity")
    @classmethod
    def validate_nonzero_delta(cls, value: Decimal) -> Decimal:
        q = _quantize_money(value)
        if q == Decimal("0.00"):
            raise ValueError("Stock adjustment delta_quantity must be non-zero.")
        return q


class ProductListResponse(BaseModel):
    """Paginated list of products or services."""

    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
