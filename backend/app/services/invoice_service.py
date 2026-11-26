"""Invoice calculation, GST split, numbering, edit history, and lifecycle service."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import Settings, get_settings
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem, InvoiceModification
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User
from app.schemas.invoice import (
    InvoiceBankSummary,
    InvoiceCreate,
    InvoiceCustomerSummary,
    InvoiceItemInput,
    InvoiceItemResponse,
    InvoiceLogoSummary,
    InvoiceModificationResponse,
    InvoiceResponse,
    InvoiceSignatureSummary,
    InvoiceThemeSummary,
    InvoiceUpdate,
)
from app.services.audit_service import record_audit_event
from app.services.media_service import delete_stored_asset
from app.services.theme_service import resolve_business_theme
from app.services.pagination import paginate_select

TWO_DP = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    """Round monetary decimals using standard ROUND_HALF_UP to 2 decimal places."""
    return value.quantize(TWO_DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ComputedLine:
    """Server-computed line amounts with CGST/SGST/IGST breakdown."""

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


@dataclass(frozen=True)
class ComputedTotals:
    """Server-computed invoice header totals."""

    subtotal_amount: Decimal
    discount_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


def resolve_gst_type(gst_mode: str, business: Business, customer: Customer) -> str:
    """Determine intra-state (cgst_sgst) vs inter-state (igst) GST split."""
    if gst_mode in {"cgst_sgst", "igst"}:
        return gst_mode
    biz_state = (business.state or "").strip().lower()
    cust_state = (customer.state or "").strip().lower()
    if biz_state and cust_state and biz_state != cust_state:
        return "igst"
    return "cgst_sgst"


def calculate_line_amounts(
    *,
    quantity: Decimal,
    unit_price: Decimal,
    discount_percent: Decimal = Decimal("0.00"),
    tax_rate: Decimal = Decimal("0.00"),
    gst_type: str = "cgst_sgst",
) -> ComputedLine:
    """Compute exact line-level subtotal, discount, CGST/SGST/IGST, and total on the server."""
    line_subtotal = round_money(quantity * unit_price)
    line_discount = round_money(line_subtotal * discount_percent / Decimal("100"))
    taxable = line_subtotal - line_discount
    line_tax = round_money(taxable * tax_rate / Decimal("100"))

    if gst_type == "igst":
        cgst_rate = Decimal("0.00")
        sgst_rate = Decimal("0.00")
        igst_rate = round_money(tax_rate)
        cgst_amount = Decimal("0.00")
        sgst_amount = Decimal("0.00")
        igst_amount = line_tax
    else:
        cgst_rate = round_money(tax_rate / Decimal("2"))
        sgst_rate = round_money(tax_rate - cgst_rate)
        igst_rate = Decimal("0.00")
        cgst_amount = round_money(line_tax / Decimal("2"))
        sgst_amount = round_money(line_tax - cgst_amount)
        igst_amount = Decimal("0.00")

    line_total = taxable + line_tax
    return ComputedLine(
        cgst_rate=cgst_rate,
        sgst_rate=sgst_rate,
        igst_rate=igst_rate,
        line_subtotal=line_subtotal,
        line_discount=line_discount,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        line_tax=line_tax,
        line_total=line_total,
    )


def calculate_invoice_totals(lines: list[ComputedLine]) -> ComputedTotals:
    """Aggregate server-computed line items into invoice header totals."""
    subtotal = sum((line.line_subtotal for line in lines), Decimal("0.00"))
    discount = sum((line.line_discount for line in lines), Decimal("0.00"))
    cgst = sum((line.cgst_amount for line in lines), Decimal("0.00"))
    sgst = sum((line.sgst_amount for line in lines), Decimal("0.00"))
    igst = sum((line.igst_amount for line in lines), Decimal("0.00"))
    tax = sum((line.line_tax for line in lines), Decimal("0.00"))
    total = subtotal - discount + tax
    return ComputedTotals(
        subtotal_amount=round_money(subtotal),
        discount_amount=round_money(discount),
        cgst_amount=round_money(cgst),
        sgst_amount=round_money(sgst),
        igst_amount=round_money(igst),
        tax_amount=round_money(tax),
        total_amount=round_money(total),
    )


def compute_effective_status(invoice: Invoice, *, today: date | None = None) -> str:
    """Derive effective invoice status including overdue check for unpaid issued invoices."""
    current_date = today or date.today()
    if (
        invoice.status in {"issued", "partially_paid"}
        and invoice.due_date < current_date
        and invoice.balance_due > Decimal("0.00")
    ):
        return "overdue"
    return invoice.status


def is_invoice_editable(invoice: Invoice) -> bool:
    """Drafts and unpaid issued invoices (amount_paid == 0) may be edited safely."""
    if invoice.status == "draft":
        return True
    if invoice.status == "issued" and invoice.amount_paid == Decimal("0.00"):
        return True
    return False


def get_invoice_deletion_policy(invoice: Invoice) -> tuple[bool, str | None]:
    """Return whether an invoice is eligible for permanent deletion under accounting rules."""
    if invoice.amount_paid > Decimal("0.00"):
        return (
            False,
            "Invoices with recorded payments cannot be deleted. Keep payment history for accounting integrity.",
        )
    if invoice.status in {"draft", "void"}:
        return True, None
    return (
        False,
        "Active issued invoices cannot be deleted directly. Cancel (void) the invoice first.",
    )


def _compute_payment_uri(business: Business | None, invoice: Invoice) -> str | None:
    if business is None or not business.upi_id:
        return None
    if invoice.status in {"draft", "void"} or invoice.balance_due <= Decimal("0.00"):
        return None
    payee_name = (business.bank_account_holder or business.name or "Business").strip()
    params = urlencode(
        {
            "pa": business.upi_id.strip(),
            "pn": payee_name[:80],
            "am": f"{invoice.balance_due:.2f}",
            "cu": invoice.currency_code,
            "tn": f"Invoice {invoice.invoice_number}",
        }
    )
    return f"upi://pay?{params}"


def _build_bank_summary(business: Business | None) -> InvoiceBankSummary | None:
    if business is None:
        return None
    has_any = any(
        [
            business.bank_account_holder,
            business.bank_name,
            business.bank_account_number,
            business.bank_ifsc_code,
            business.bank_branch,
            business.upi_id,
        ]
    )
    if not has_any:
        return None
    return InvoiceBankSummary(
        bank_account_holder=business.bank_account_holder,
        bank_name=business.bank_name,
        bank_account_number=business.bank_account_number,
        bank_ifsc_code=business.bank_ifsc_code,
        bank_branch=business.bank_branch,
        upi_id=business.upi_id,
    )


def _build_signature_summary(business: Business | None) -> InvoiceSignatureSummary | None:
    if business is None:
        return None
    return InvoiceSignatureSummary(
        has_signature=bool(business.signature_storage_key),
        signature_enabled=bool(business.signature_enabled),
        signature_placement=business.signature_placement or "bottom_right",
        signature_updated_at=business.signature_updated_at,
    )


def _build_logo_summary(business: Business | None) -> InvoiceLogoSummary | None:
    if business is None:
        return None
    return InvoiceLogoSummary(
        has_logo=bool(business.logo_storage_key),
        logo_updated_at=business.logo_updated_at,
    )


def _build_theme_summary(business: Business | None) -> InvoiceThemeSummary:
    return InvoiceThemeSummary(**resolve_business_theme(business))


def serialize_invoice(invoice: Invoice) -> InvoiceResponse:
    """Map an ORM Invoice to InvoiceResponse without exposing internal storage keys."""
    payment_uri = _compute_payment_uri(invoice.business, invoice)
    can_delete, delete_reason = get_invoice_deletion_policy(invoice)
    return InvoiceResponse(
        id=invoice.id,
        business_id=invoice.business_id,
        customer_id=invoice.customer_id,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        effective_status=compute_effective_status(invoice),
        gst_mode=invoice.gst_mode,
        gst_type=invoice.gst_type,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        currency_code=invoice.currency_code,
        subtotal_amount=invoice.subtotal_amount,
        discount_amount=invoice.discount_amount,
        cgst_amount=invoice.cgst_amount,
        sgst_amount=invoice.sgst_amount,
        igst_amount=invoice.igst_amount,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        amount_paid=invoice.amount_paid,
        balance_due=invoice.balance_due,
        notes=invoice.notes,
        terms=invoice.terms,
        has_pdf=bool(invoice.pdf_storage_key),
        is_editable=is_invoice_editable(invoice),
        is_deletable=can_delete,
        delete_block_reason=delete_reason,
        payment_qr_available=bool(payment_uri),
        payment_uri=payment_uri,
        bank_details=_build_bank_summary(invoice.business),
        signature=_build_signature_summary(invoice.business),
        logo=_build_logo_summary(invoice.business),
        theme=_build_theme_summary(invoice.business),
        pdf_generated_at=invoice.pdf_generated_at,
        issued_at=invoice.issued_at,
        cancelled_at=invoice.cancelled_at,
        cancellation_reason=invoice.cancellation_reason,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        customer=InvoiceCustomerSummary.model_validate(invoice.customer),
        items=[InvoiceItemResponse.model_validate(item) for item in invoice.items],
        modifications=[
            InvoiceModificationResponse.model_validate(mod)
            for mod in invoice.modifications
        ],
    )


def record_invoice_modification(
    db: Session,
    *,
    invoice: Invoice,
    current_user: User,
    action: str,
    summary: str,
    changes: dict[str, Any] | None = None,
) -> InvoiceModification:
    """Append an immutable invoice modification history entry."""
    entry = InvoiceModification(
        business_id=invoice.business_id,
        invoice_id=invoice.id,
        modified_by_user_id=current_user.id,
        modified_by_name=current_user.full_name,
        modified_by_email=current_user.email,
        action=action,
        summary=summary,
        changes_json=changes,
    )
    db.add(entry)
    return entry


def _validate_owned_customer(db: Session, *, business_id: int, customer_id: int) -> Customer:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.business_id == business_id,
        )
    )
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Selected customer was not found for this business.",
        )
    return customer


def _validate_owned_products(
    db: Session,
    *,
    business_id: int,
    items: list[InvoiceItemInput],
) -> dict[int, Product]:
    product_ids = {item.product_id for item in items if item.product_id is not None}
    if not product_ids:
        return {}
    products = list(
        db.scalars(
            select(Product).where(
                Product.business_id == business_id,
                Product.id.in_(product_ids),
            )
        ).all()
    )
    product_map = {p.id: p for p in products}
    if len(product_map) != len(product_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more selected products do not belong to this business.",
        )
    return product_map


def _build_invoice_items(
    items_input: list[InvoiceItemInput],
    product_map: dict[int, Product],
    *,
    gst_type: str,
) -> tuple[list[InvoiceItem], ComputedTotals]:
    orm_items: list[InvoiceItem] = []
    computed_lines: list[ComputedLine] = []

    for idx, line in enumerate(items_input, start=1):
        resolved_hsn = line.hsn_code
        if line.product_id is not None:
            product = product_map[line.product_id]
            if not resolved_hsn:
                resolved_hsn = product.hsn_code
        calc = calculate_line_amounts(
            quantity=line.quantity,
            unit_price=line.unit_price,
            discount_percent=line.discount_percent,
            tax_rate=line.tax_rate,
            gst_type=gst_type,
        )
        computed_lines.append(calc)
        orm_items.append(
            InvoiceItem(
                product_id=line.product_id,
                position=idx,
                item_name=line.item_name,
                hsn_code=resolved_hsn,
                description=line.description,
                unit=line.unit,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                tax_rate=line.tax_rate,
                tax_label=line.tax_label,
                cgst_rate=calc.cgst_rate,
                sgst_rate=calc.sgst_rate,
                igst_rate=calc.igst_rate,
                line_subtotal=calc.line_subtotal,
                line_discount=calc.line_discount,
                cgst_amount=calc.cgst_amount,
                sgst_amount=calc.sgst_amount,
                igst_amount=calc.igst_amount,
                line_tax=calc.line_tax,
                line_total=calc.line_total,
            )
        )

    return orm_items, calculate_invoice_totals(computed_lines)


def get_owned_invoice(db: Session, *, business_id: int, invoice_id: int) -> Invoice:
    """Fetch an invoice with customer, business, items, and modification history."""
    invoice = db.scalar(
        select(Invoice)
        .options(
            joinedload(Invoice.customer),
            joinedload(Invoice.business),
            selectinload(Invoice.items),
            selectinload(Invoice.modifications),
        )
        .execution_options(populate_existing=True)
        .where(
            Invoice.id == invoice_id,
            Invoice.business_id == business_id,
        )
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    return invoice


def list_invoices(
    db: Session,
    *,
    business_id: int,
    q: str | None = None,
    status_filter: str | None = None,
    customer_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Invoice], int, int]:
    """Search, filter, and paginate invoices owned by business_id."""
    stmt = (
        select(Invoice)
        .join(Customer, Invoice.customer_id == Customer.id)
        .options(
            joinedload(Invoice.customer),
            joinedload(Invoice.business),
            selectinload(Invoice.items),
            selectinload(Invoice.modifications),
        )
        .where(Invoice.business_id == business_id)
    )

    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if date_from is not None:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Invoice.issue_date <= date_to)

    if status_filter:
        today = date.today()
        if status_filter == "overdue":
            stmt = stmt.where(
                Invoice.status.in_(["issued", "partially_paid"]),
                Invoice.due_date < today,
                Invoice.balance_due > Decimal("0.00"),
            )
        elif status_filter in {"issued", "partially_paid"}:
            stmt = stmt.where(
                and_(
                    Invoice.status == status_filter,
                    Invoice.due_date >= today,
                )
            )
        else:
            stmt = stmt.where(Invoice.status == status_filter)

    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Invoice.invoice_number.ilike(term),
                Customer.name.ilike(term),
                Customer.company_name.ilike(term),
            )
        )

    stmt = stmt.order_by(Invoice.issue_date.desc(), Invoice.id.desc())
    return paginate_select(db, stmt, page=page, page_size=page_size)


def create_invoice(
    db: Session,
    *,
    current_user: User,
    payload: InvoiceCreate,
) -> Invoice:
    """Create an invoice and line items atomically with server-side GST calculations."""
    business_id = current_user.business_id
    customer = _validate_owned_customer(
        db, business_id=business_id, customer_id=payload.customer_id
    )
    product_map = _validate_owned_products(db, business_id=business_id, items=payload.items)

    # Lock business row to assign a unique sequential invoice number atomically
    business = db.scalar(
        select(Business).where(Business.id == business_id).with_for_update()
    )
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    seq_num = business.next_invoice_number
    invoice_number = f"{business.invoice_prefix}{seq_num}"
    business.next_invoice_number = seq_num + 1

    gst_type = resolve_gst_type(payload.gst_mode, business, customer)
    orm_items, totals = _build_invoice_items(
        payload.items, product_map, gst_type=gst_type
    )
    now = datetime.now(timezone.utc)
    initial_status = "issued" if payload.issue_immediately else "draft"

    invoice = Invoice(
        business_id=business_id,
        customer_id=payload.customer_id,
        invoice_number=invoice_number,
        status=initial_status,
        gst_mode=payload.gst_mode,
        gst_type=gst_type,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        currency_code=business.currency_code,
        subtotal_amount=totals.subtotal_amount,
        discount_amount=totals.discount_amount,
        cgst_amount=totals.cgst_amount,
        sgst_amount=totals.sgst_amount,
        igst_amount=totals.igst_amount,
        tax_amount=totals.tax_amount,
        total_amount=totals.total_amount,
        amount_paid=Decimal("0.00"),
        balance_due=totals.total_amount,
        notes=payload.notes,
        terms=payload.terms,
        issued_at=now if payload.issue_immediately else None,
        items=orm_items,
    )
    db.add(invoice)
    db.flush()

    record_invoice_modification(
        db,
        invoice=invoice,
        current_user=current_user,
        action="created",
        summary=f"Created {initial_status} invoice {invoice.invoice_number} ({invoice.currency_code} {invoice.total_amount:.2f}).",
        changes={
            "status": initial_status,
            "gst_type": gst_type,
            "total_amount": str(invoice.total_amount),
            "item_count": len(orm_items),
        },
    )

    record_audit_event(
        db,
        business_id=business_id,
        user_id=current_user.id,
        action="invoice.created",
        entity_type="invoice",
        entity_id=invoice.id,
        details={
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "gst_type": gst_type,
            "total_amount": str(invoice.total_amount),
        },
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice number conflict occurred. Please try again.",
        ) from exc

    return get_owned_invoice(db, business_id=business_id, invoice_id=invoice.id)


def update_invoice(
    db: Session,
    *,
    current_user: User,
    invoice_id: int,
    payload: InvoiceUpdate,
) -> tuple[Invoice, bool]:
    """Update an editable invoice (draft or unpaid issued), recording before/after diffs."""
    business_id = current_user.business_id
    invoice = get_owned_invoice(db, business_id=business_id, invoice_id=invoice_id)

    if not is_invoice_editable(invoice):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Paid, partially paid, or cancelled invoices cannot be edited.",
        )

    customer = _validate_owned_customer(
        db, business_id=business_id, customer_id=payload.customer_id
    )
    product_map = _validate_owned_products(db, business_id=business_id, items=payload.items)
    gst_type = resolve_gst_type(payload.gst_mode, invoice.business, customer)
    orm_items, totals = _build_invoice_items(
        payload.items, product_map, gst_type=gst_type
    )

    had_pdf = bool(invoice.pdf_storage_key)

    # Capture before/after diff for modification history
    changes: dict[str, dict[str, Any]] = {}
    if invoice.customer_id != payload.customer_id:
        changes["customer"] = {
            "before": invoice.customer.name if invoice.customer else str(invoice.customer_id),
            "after": customer.name,
        }
    if invoice.issue_date != payload.issue_date:
        changes["issue_date"] = {
            "before": invoice.issue_date.isoformat(),
            "after": payload.issue_date.isoformat(),
        }
    if invoice.due_date != payload.due_date:
        changes["due_date"] = {
            "before": invoice.due_date.isoformat(),
            "after": payload.due_date.isoformat(),
        }
    if invoice.gst_type != gst_type:
        changes["gst_type"] = {"before": invoice.gst_type, "after": gst_type}
    if invoice.total_amount != totals.total_amount:
        changes["total_amount"] = {
            "before": str(invoice.total_amount),
            "after": str(totals.total_amount),
        }
    if invoice.tax_amount != totals.tax_amount:
        changes["tax_amount"] = {
            "before": str(invoice.tax_amount),
            "after": str(totals.tax_amount),
        }
    old_items_summary = [
        f"{it.item_name} x{it.quantity}" for it in invoice.items
    ]
    new_items_summary = [
        f"{it.item_name} x{it.quantity}" for it in orm_items
    ]
    if old_items_summary != new_items_summary or invoice.subtotal_amount != totals.subtotal_amount:
        changes["items"] = {
            "before": old_items_summary,
            "after": new_items_summary,
        }

    invoice.customer_id = payload.customer_id
    invoice.gst_mode = payload.gst_mode
    invoice.gst_type = gst_type
    invoice.issue_date = payload.issue_date
    invoice.due_date = payload.due_date
    invoice.notes = payload.notes
    invoice.terms = payload.terms
    invoice.subtotal_amount = totals.subtotal_amount
    invoice.discount_amount = totals.discount_amount
    invoice.cgst_amount = totals.cgst_amount
    invoice.sgst_amount = totals.sgst_amount
    invoice.igst_amount = totals.igst_amount
    invoice.tax_amount = totals.tax_amount
    invoice.total_amount = totals.total_amount
    invoice.balance_due = round_money(totals.total_amount - invoice.amount_paid)
    invoice.pdf_storage_key = None
    invoice.pdf_generated_at = None

    invoice.items.clear()
    db.flush()
    invoice.items.extend(orm_items)

    changed_keys = ", ".join(changes.keys()) if changes else "details"
    record_invoice_modification(
        db,
        invoice=invoice,
        current_user=current_user,
        action="edited",
        summary=f"Edited invoice {invoice.invoice_number} ({changed_keys}).",
        changes=changes or None,
    )

    record_audit_event(
        db,
        business_id=business_id,
        user_id=current_user.id,
        action="invoice.updated",
        entity_type="invoice",
        entity_id=invoice.id,
        details={
            "invoice_number": invoice.invoice_number,
            "changed": list(changes.keys()),
            "total_amount": str(totals.total_amount),
        },
    )
    db.commit()
    return get_owned_invoice(db, business_id=business_id, invoice_id=invoice.id), had_pdf


def issue_invoice(
    db: Session,
    *,
    current_user: User,
    invoice_id: int,
) -> Invoice:
    """Transition a draft invoice to issued."""
    invoice = get_owned_invoice(
        db, business_id=current_user.business_id, invoice_id=invoice_id
    )
    if invoice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft invoices can be issued.",
        )

    invoice.status = "issued"
    invoice.issued_at = datetime.now(timezone.utc)
    invoice.pdf_storage_key = None
    invoice.pdf_generated_at = None

    record_invoice_modification(
        db,
        invoice=invoice,
        current_user=current_user,
        action="issued",
        summary=f"Issued invoice {invoice.invoice_number}.",
        changes={"status": {"before": "draft", "after": "issued"}},
    )
    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="invoice.issued",
        entity_type="invoice",
        entity_id=invoice.id,
        details={"invoice_number": invoice.invoice_number},
    )
    db.commit()
    return get_owned_invoice(db, business_id=current_user.business_id, invoice_id=invoice.id)


def void_invoice(
    db: Session,
    *,
    current_user: User,
    invoice_id: int,
    reason: str | None = None,
) -> Invoice:
    """Cancel/void an unpaid invoice while preserving financial and audit records."""
    invoice = get_owned_invoice(
        db, business_id=current_user.business_id, invoice_id=invoice_id
    )
    if invoice.status == "void":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice is already cancelled.",
        )
    if invoice.amount_paid > Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot cancel an invoice that already has recorded payments.",
        )

    previous_status = invoice.status
    invoice.status = "void"
    invoice.balance_due = Decimal("0.00")
    invoice.cancelled_at = datetime.now(timezone.utc)
    invoice.cancellation_reason = reason
    invoice.pdf_storage_key = None
    invoice.pdf_generated_at = None

    record_invoice_modification(
        db,
        invoice=invoice,
        current_user=current_user,
        action="cancelled",
        summary=f"Cancelled invoice {invoice.invoice_number}."
        + (f" Reason: {reason}" if reason else ""),
        changes={
            "status": {"before": previous_status, "after": "void"},
            **({"reason": reason} if reason else {}),
        },
    )
    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="invoice.voided",
        entity_type="invoice",
        entity_id=invoice.id,
        details={
            "invoice_number": invoice.invoice_number,
            "previous_status": previous_status,
            **({"reason": reason} if reason else {}),
        },
    )
    db.commit()
    return get_owned_invoice(db, business_id=current_user.business_id, invoice_id=invoice.id)


def delete_draft_invoice(
    db: Session,
    *,
    current_user: User,
    invoice_id: int,
    settings: Settings | None = None,
) -> None:
    """Permanently delete an eligible (draft or unpaid void) invoice inside a transaction."""
    active_settings = settings or get_settings()
    invoice = db.scalar(
        select(Invoice)
        .where(
            Invoice.id == invoice_id,
            Invoice.business_id == current_user.business_id,
        )
        .with_for_update()
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    payment_count = (
        db.scalar(
            select(func.count(Payment.id)).where(
                Payment.business_id == current_user.business_id,
                Payment.invoice_id == invoice.id,
            )
        )
        or 0
    )
    if payment_count > 0 or invoice.amount_paid > Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot permanently delete an invoice that has recorded payments.",
        )

    if invoice.status not in {"draft", "void"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft or cancelled unpaid invoices can be permanently deleted. Cancel active issued invoices first.",
        )

    inv_number = invoice.invoice_number
    prev_status = invoice.status
    pdf_key = invoice.pdf_storage_key

    try:
        db.delete(invoice)
        record_audit_event(
            db,
            business_id=current_user.business_id,
            user_id=current_user.id,
            action="invoice.deleted",
            entity_type="invoice",
            entity_id=invoice_id,
            details={"invoice_number": inv_number, "previous_status": prev_status},
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete invoice cleanly due to a database constraint.",
        ) from exc

    try:
        delete_stored_asset(
            active_settings.resolved_pdf_dir,
            pdf_key,
            asset_label="pdf",
            namespace="pdfs",
            settings=active_settings,
        )
    except Exception:
        # Storage cleanup failure should not undo a committed database deletion.
        pass
