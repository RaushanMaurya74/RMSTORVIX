"""Pydantic schemas for Payment recording and listings."""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import OptionalCleanText

PaymentMethodType = Literal[
    "bank_transfer",
    "cash",
    "card",
    "upi",
    "cheque",
    "other",
]


class PaymentCreate(BaseModel):
    """Payload to record a payment against an issued invoice."""

    invoice_id: int = Field(ge=1)
    amount: Decimal = Field(gt=Decimal("0.00"), le=Decimal("999999999.99"))
    payment_date: date
    payment_method: PaymentMethodType = Field(default="bank_transfer")
    reference: OptionalCleanText = Field(default=None, max_length=120)
    notes: OptionalCleanText = Field(default=None, max_length=2000)

    @field_validator("amount")
    @classmethod
    def quantize_amount(cls, value: Decimal) -> Decimal:
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if quantized <= Decimal("0.00"):
            raise ValueError("Payment amount must be greater than 0.00.")
        return quantized


class PaymentResponse(BaseModel):
    """Serialized payment entry with invoice and customer context."""

    id: int
    business_id: int
    invoice_id: int
    invoice_number: str
    customer_name: str
    currency_code: str
    amount: Decimal
    payment_date: date
    payment_method: str
    reference: str | None = None
    notes: str | None = None
    created_at: datetime


class PaymentListResponse(BaseModel):
    """Paginated list of payments."""

    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
