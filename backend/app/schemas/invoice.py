"""Pydantic schemas for Invoices, GST split, modification history, and bank/QR info."""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import OptionalCleanText, OptionalHsnCode


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


InvoiceStatusType = Literal[
    "draft",
    "issued",
    "partially_paid",
    "paid",
    "overdue",
    "void",
]

GstModeType = Literal["auto", "cgst_sgst", "igst"]


class InvoiceItemInput(BaseModel):
    """Input line item submitted by client; totals are always calculated on the server."""

    product_id: int | None = Field(default=None, ge=1)
    item_name: str = Field(min_length=1, max_length=160)
    hsn_code: OptionalHsnCode = None
    description: OptionalCleanText = Field(default=None, max_length=2000)
    unit: OptionalCleanText = Field(default=None, max_length=32)
    quantity: Decimal = Field(gt=Decimal("0.00"), le=Decimal("999999.99"))
    unit_price: Decimal = Field(ge=Decimal("0.00"), le=Decimal("999999999.99"))
    discount_percent: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
    )
    tax_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
    )
    tax_label: OptionalCleanText = Field(default=None, max_length=40)

    @field_validator("item_name")
    @classmethod
    def strip_item_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Line item name cannot be blank.")
        return cleaned

    @field_validator("quantity", "unit_price", "discount_percent", "tax_rate")
    @classmethod
    def quantize_decimals(cls, value: Decimal) -> Decimal:
        return _q2(value)


class InvoiceBaseInput(BaseModel):
    """Shared invoice creation and update payload."""

    customer_id: int = Field(ge=1)
    issue_date: date
    due_date: date
    gst_mode: GstModeType = Field(default="auto")
    notes: OptionalCleanText = Field(default=None, max_length=3000)
    terms: OptionalCleanText = Field(default=None, max_length=3000)
    items: list[InvoiceItemInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_dates(self) -> "InvoiceBaseInput":
        if self.due_date < self.issue_date:
            raise ValueError("Due date cannot be earlier than issue date.")
        return self


class InvoiceCreate(InvoiceBaseInput):
    """Payload to create an invoice as draft or immediately issued."""

    issue_immediately: bool = Field(default=False)


class InvoiceUpdate(InvoiceBaseInput):
    """Payload to update an editable invoice."""


class InvoiceVoidRequest(BaseModel):
    """Optional cancellation reason when voiding an unpaid invoice."""

    reason: OptionalCleanText = Field(default=None, max_length=500)


class InvoiceCustomerSummary(BaseModel):
    """Safe customer snapshot displayed on invoice views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    tax_id: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class InvoiceBankSummary(BaseModel):
    """Business bank & UPI payment configuration displayed on invoices."""

    bank_account_holder: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    bank_branch: str | None = None
    upi_id: str | None = None


class InvoiceSignatureSummary(BaseModel):
    """Authorized visual signature metadata for invoice preview (no file paths)."""

    has_signature: bool
    signature_enabled: bool
    signature_placement: str
    signature_updated_at: datetime | None = None


class InvoiceLogoSummary(BaseModel):
    """Authorized business logo metadata for invoice preview (no file paths)."""

    has_logo: bool
    logo_updated_at: datetime | None = None


class InvoiceThemeSummary(BaseModel):
    """Resolved invoice appearance palette attached to invoice preview payloads."""

    preset: str
    primary_color: str
    secondary_color: str
    accent_color: str
    header_color: str
    table_header_color: str
    text_color: str
    border_color: str


class InvoiceItemResponse(BaseModel):
    """Serialized server-calculated invoice line item with HSN and GST breakdown."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = None
    position: int
    item_name: str
    hsn_code: str | None = None
    description: str | None = None
    unit: str | None = None
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    tax_rate: Decimal
    tax_label: str | None = None
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    line_subtotal: Decimal
    line_discount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    line_tax: Decimal
    line_total: Decimal


class InvoiceModificationResponse(BaseModel):
    """Serialized invoice modification history record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    modified_by_name: str
    modified_by_email: str
    action: str
    summary: str
    changes_json: dict[str, Any] | None = None
    created_at: datetime


class InvoiceResponse(BaseModel):
    """Serialized invoice record (never exposes internal PDF file paths)."""

    id: int
    business_id: int
    customer_id: int
    invoice_number: str
    status: str
    effective_status: str
    gst_mode: str
    gst_type: str
    issue_date: date
    due_date: date
    currency_code: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    notes: str | None = None
    terms: str | None = None
    has_pdf: bool
    is_editable: bool
    is_deletable: bool = False
    delete_block_reason: str | None = None
    payment_qr_available: bool
    payment_uri: str | None = None
    bank_details: InvoiceBankSummary | None = None
    signature: InvoiceSignatureSummary | None = None
    logo: InvoiceLogoSummary | None = None
    theme: InvoiceThemeSummary | None = None
    pdf_generated_at: datetime | None = None
    issued_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    customer: InvoiceCustomerSummary
    items: list[InvoiceItemResponse]
    modifications: list[InvoiceModificationResponse]


class InvoiceListResponse(BaseModel):
    """Paginated list of invoices."""

    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
