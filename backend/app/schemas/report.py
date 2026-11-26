"""Pydantic schemas for sales/invoice summaries, HSN summary, and audit trail responses."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class StatusBreakdownItem(BaseModel):
    """Count and total amount for a given invoice status."""

    status: str
    count: int
    total_amount: Decimal


class TopCustomerSummary(BaseModel):
    """Aggregated billing summary per customer."""

    customer_id: int
    customer_name: str
    invoice_count: int
    total_billed: Decimal
    total_paid: Decimal
    balance_due: Decimal


class HsnSummaryItem(BaseModel):
    """Aggregated HSN summary across billed invoice items."""

    hsn_code: str
    item_count: int
    total_quantity: Decimal
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax: Decimal
    total_value: Decimal


class SalesReportResponse(BaseModel):
    """Business-scoped sales, tax, collections, HSN, and status summary."""

    currency_code: str
    date_from: date | None = None
    date_to: date | None = None
    total_invoices: int
    draft_count: int
    issued_count: int
    partially_paid_count: int
    paid_count: int
    overdue_count: int
    void_count: int
    total_billed: Decimal
    total_cgst: Decimal
    total_sgst: Decimal
    total_igst: Decimal
    total_tax: Decimal
    total_paid_on_invoices: Decimal
    total_outstanding: Decimal
    total_collected_payments: Decimal
    status_breakdown: list[StatusBreakdownItem]
    top_customers: list[TopCustomerSummary]
    hsn_summary: list[HsnSummaryItem]


class AuditEventResponse(BaseModel):
    """Read-only audit event record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    user_id: int | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    details_json: dict[str, Any] | None = None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    """Paginated audit trail response."""

    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
