"""Sales, invoice summary, HSN summary, CSV export, and audit trail service."""

import csv
from datetime import date
from decimal import Decimal
import io

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.audit_event import AuditEvent
from app.models.business import Business
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.schemas.report import (
    HsnSummaryItem,
    SalesReportResponse,
    StatusBreakdownItem,
    TopCustomerSummary,
)
from app.services.invoice_service import compute_effective_status, round_money
from app.services.pagination import paginate_select


def _validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="End date cannot be earlier than start date.",
        )


def _safe_csv_cell(value: object) -> str:
    """Neutralize spreadsheet formula injection characters in exported CSV cells."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def get_sales_summary(
    db: Session,
    *,
    business_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SalesReportResponse:
    """Aggregate sales, GST split, HSN summary, collections, and top customers."""
    _validate_date_range(date_from, date_to)

    business = db.scalar(select(Business).where(Business.id == business_id))
    currency_code = business.currency_code if business else "USD"

    inv_stmt = (
        select(Invoice)
        .options(joinedload(Invoice.customer), selectinload(Invoice.items))
        .where(Invoice.business_id == business_id)
    )
    if date_from is not None:
        inv_stmt = inv_stmt.where(Invoice.issue_date >= date_from)
    if date_to is not None:
        inv_stmt = inv_stmt.where(Invoice.issue_date <= date_to)

    invoices = list(db.scalars(inv_stmt).all())

    pay_stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.business_id == business_id
    )
    if date_from is not None:
        pay_stmt = pay_stmt.where(Payment.payment_date >= date_from)
    if date_to is not None:
        pay_stmt = pay_stmt.where(Payment.payment_date <= date_to)
    total_collected_payments = round_money(Decimal(str(db.scalar(pay_stmt) or 0)))

    counts: dict[str, int] = {
        "draft": 0,
        "issued": 0,
        "partially_paid": 0,
        "paid": 0,
        "overdue": 0,
        "void": 0,
    }
    status_totals: dict[str, Decimal] = {k: Decimal("0.00") for k in counts}

    total_billed = Decimal("0.00")
    total_cgst = Decimal("0.00")
    total_sgst = Decimal("0.00")
    total_igst = Decimal("0.00")
    total_tax = Decimal("0.00")
    total_paid_on_invoices = Decimal("0.00")
    total_outstanding = Decimal("0.00")
    customer_agg: dict[int, dict] = {}
    hsn_agg: dict[str, dict] = {}

    today = date.today()
    for inv in invoices:
        eff = compute_effective_status(inv, today=today)
        counts[eff] = counts.get(eff, 0) + 1
        status_totals[eff] = round_money(
            status_totals.get(eff, Decimal("0.00")) + inv.total_amount
        )

        if inv.status not in {"draft", "void"}:
            total_billed += inv.total_amount
            total_cgst += inv.cgst_amount
            total_sgst += inv.sgst_amount
            total_igst += inv.igst_amount
            total_tax += inv.tax_amount
            total_paid_on_invoices += inv.amount_paid
            total_outstanding += inv.balance_due

            entry = customer_agg.setdefault(
                inv.customer_id,
                {
                    "customer_id": inv.customer_id,
                    "customer_name": inv.customer.name if inv.customer else "—",
                    "invoice_count": 0,
                    "total_billed": Decimal("0.00"),
                    "total_paid": Decimal("0.00"),
                    "balance_due": Decimal("0.00"),
                },
            )
            entry["invoice_count"] += 1
            entry["total_billed"] = round_money(entry["total_billed"] + inv.total_amount)
            entry["total_paid"] = round_money(entry["total_paid"] + inv.amount_paid)
            entry["balance_due"] = round_money(entry["balance_due"] + inv.balance_due)

            for item in inv.items:
                hsn_key = item.hsn_code or "Unassigned"
                taxable = item.line_subtotal - item.line_discount
                h_entry = hsn_agg.setdefault(
                    hsn_key,
                    {
                        "hsn_code": hsn_key,
                        "item_count": 0,
                        "total_quantity": Decimal("0.00"),
                        "taxable_value": Decimal("0.00"),
                        "cgst_amount": Decimal("0.00"),
                        "sgst_amount": Decimal("0.00"),
                        "igst_amount": Decimal("0.00"),
                        "total_tax": Decimal("0.00"),
                        "total_value": Decimal("0.00"),
                    },
                )
                h_entry["item_count"] += 1
                h_entry["total_quantity"] = round_money(
                    h_entry["total_quantity"] + item.quantity
                )
                h_entry["taxable_value"] = round_money(
                    h_entry["taxable_value"] + taxable
                )
                h_entry["cgst_amount"] = round_money(
                    h_entry["cgst_amount"] + item.cgst_amount
                )
                h_entry["sgst_amount"] = round_money(
                    h_entry["sgst_amount"] + item.sgst_amount
                )
                h_entry["igst_amount"] = round_money(
                    h_entry["igst_amount"] + item.igst_amount
                )
                h_entry["total_tax"] = round_money(
                    h_entry["total_tax"] + item.line_tax
                )
                h_entry["total_value"] = round_money(
                    h_entry["total_value"] + item.line_total
                )

    status_breakdown = [
        StatusBreakdownItem(
            status=st,
            count=counts[st],
            total_amount=status_totals[st],
        )
        for st in ["draft", "issued", "partially_paid", "paid", "overdue", "void"]
    ]

    top_customers = [
        TopCustomerSummary(**item)
        for item in sorted(
            customer_agg.values(),
            key=lambda x: x["total_billed"],
            reverse=True,
        )[:10]
    ]

    hsn_summary = [
        HsnSummaryItem(**item)
        for item in sorted(
            hsn_agg.values(),
            key=lambda x: (x["hsn_code"] == "Unassigned", -x["total_value"]),
        )
    ]

    return SalesReportResponse(
        currency_code=currency_code,
        date_from=date_from,
        date_to=date_to,
        total_invoices=len(invoices),
        draft_count=counts["draft"],
        issued_count=counts["issued"],
        partially_paid_count=counts["partially_paid"],
        paid_count=counts["paid"],
        overdue_count=counts["overdue"],
        void_count=counts["void"],
        total_billed=round_money(total_billed),
        total_cgst=round_money(total_cgst),
        total_sgst=round_money(total_sgst),
        total_igst=round_money(total_igst),
        total_tax=round_money(total_tax),
        total_paid_on_invoices=round_money(total_paid_on_invoices),
        total_outstanding=round_money(total_outstanding),
        total_collected_payments=total_collected_payments,
        status_breakdown=status_breakdown,
        top_customers=top_customers,
        hsn_summary=hsn_summary,
    )


def export_invoices_csv(
    db: Session,
    *,
    business_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> str:
    """Generate a business-scoped CSV export of invoices with GST breakdown."""
    _validate_date_range(date_from, date_to)

    stmt = (
        select(Invoice)
        .options(joinedload(Invoice.customer))
        .where(Invoice.business_id == business_id)
    )
    if date_from is not None:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    stmt = stmt.order_by(Invoice.issue_date.desc(), Invoice.id.desc())

    invoices = list(db.scalars(stmt).all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Invoice Number",
            "Status",
            "GST Type",
            "Customer",
            "Issue Date",
            "Due Date",
            "Currency",
            "Subtotal",
            "Discount",
            "CGST",
            "SGST",
            "IGST",
            "Total Tax",
            "Total",
            "Amount Paid",
            "Balance Due",
        ]
    )
    today = date.today()
    for inv in invoices:
        writer.writerow(
            [
                _safe_csv_cell(inv.invoice_number),
                _safe_csv_cell(compute_effective_status(inv, today=today)),
                _safe_csv_cell(inv.gst_type),
                _safe_csv_cell(inv.customer.name if inv.customer else ""),
                inv.issue_date.isoformat(),
                inv.due_date.isoformat(),
                _safe_csv_cell(inv.currency_code),
                f"{inv.subtotal_amount:.2f}",
                f"{inv.discount_amount:.2f}",
                f"{inv.cgst_amount:.2f}",
                f"{inv.sgst_amount:.2f}",
                f"{inv.igst_amount:.2f}",
                f"{inv.tax_amount:.2f}",
                f"{inv.total_amount:.2f}",
                f"{inv.amount_paid:.2f}",
                f"{inv.balance_due:.2f}",
            ]
        )
    return buf.getvalue()


def list_audit_events(
    db: Session,
    *,
    business_id: int,
    action: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditEvent], int, int]:
    """List append-only audit events scoped to business_id."""
    stmt = select(AuditEvent).where(AuditEvent.business_id == business_id)
    if action:
        stmt = stmt.where(AuditEvent.action.ilike(f"%{action.strip()}%"))
    stmt = stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    return paginate_select(db, stmt, page=page, page_size=page_size)
