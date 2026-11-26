"""Payment recording, reversal, and invoice balance synchronization service."""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentResponse
from app.services.audit_service import record_audit_event
from app.services.invoice_service import record_invoice_modification, round_money
from app.services.pagination import paginate_select


def serialize_payment(payment: Payment) -> PaymentResponse:
    """Map Payment + joined Invoice/Customer into PaymentResponse."""
    inv = payment.invoice
    return PaymentResponse(
        id=payment.id,
        business_id=payment.business_id,
        invoice_id=payment.invoice_id,
        invoice_number=inv.invoice_number,
        customer_name=inv.customer.name if inv.customer else "—",
        currency_code=inv.currency_code,
        amount=payment.amount,
        payment_date=payment.payment_date,
        payment_method=payment.payment_method,
        reference=payment.reference,
        notes=payment.notes,
        created_at=payment.created_at,
    )


def list_payments(
    db: Session,
    *,
    business_id: int,
    q: str | None = None,
    invoice_id: int | None = None,
    payment_method: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Payment], int, int]:
    """Search, filter, and paginate payments owned by business_id."""
    stmt = (
        select(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(Customer, Invoice.customer_id == Customer.id)
        .options(joinedload(Payment.invoice).joinedload(Invoice.customer))
        .where(Payment.business_id == business_id)
    )

    if invoice_id is not None:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if payment_method:
        stmt = stmt.where(Payment.payment_method == payment_method)
    if date_from is not None:
        stmt = stmt.where(Payment.payment_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Payment.payment_date <= date_to)

    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Invoice.invoice_number.ilike(term),
                Customer.name.ilike(term),
                Payment.reference.ilike(term),
            )
        )

    stmt = stmt.order_by(Payment.payment_date.desc(), Payment.id.desc())
    return paginate_select(db, stmt, page=page, page_size=page_size)


def record_payment(
    db: Session,
    *,
    current_user: User,
    payload: PaymentCreate,
) -> Payment:
    """Record a payment and update invoice amount_paid, balance_due, and status atomically."""
    business_id = current_user.business_id
    invoice = db.scalar(
        select(Invoice)
        .where(
            Invoice.id == payload.invoice_id,
            Invoice.business_id == business_id,
        )
        .with_for_update()
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )

    if invoice.status in {"draft", "void"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payments can only be recorded for issued invoices.",
        )

    if invoice.balance_due <= Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invoice is already paid in full.",
        )

    if payload.amount > invoice.balance_due:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment amount cannot exceed the remaining balance due.",
        )

    payment = Payment(
        business_id=business_id,
        invoice_id=invoice.id,
        amount=payload.amount,
        payment_date=payload.payment_date,
        payment_method=payload.payment_method,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(payment)
    db.flush()

    new_paid = round_money(invoice.amount_paid + payload.amount)
    new_balance = round_money(invoice.total_amount - new_paid)
    if new_balance < Decimal("0.00"):
        new_balance = Decimal("0.00")

    invoice.amount_paid = new_paid
    invoice.balance_due = new_balance
    invoice.status = "paid" if new_balance == Decimal("0.00") else "partially_paid"
    invoice.pdf_storage_key = None
    invoice.pdf_generated_at = None

    record_invoice_modification(
        db,
        invoice=invoice,
        current_user=current_user,
        action="payment_recorded",
        summary=f"Recorded payment of {invoice.currency_code} {payment.amount:.2f} via {payment.payment_method}.",
        changes={
            "amount_paid": str(new_paid),
            "balance_due": str(new_balance),
            "status": invoice.status,
        },
    )
    record_audit_event(
        db,
        business_id=business_id,
        user_id=current_user.id,
        action="payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        details={
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "amount": str(payment.amount),
            "payment_method": payment.payment_method,
            "new_status": invoice.status,
        },
    )
    db.commit()

    return db.scalar(
        select(Payment)
        .options(joinedload(Payment.invoice).joinedload(Invoice.customer))
        .where(Payment.id == payment.id)
    )  # type: ignore[return-value]


def delete_payment(
    db: Session,
    *,
    current_user: User,
    payment_id: int,
) -> None:
    """Reverse/delete an owned payment and restore the invoice balance and status."""
    business_id = current_user.business_id
    payment = db.scalar(
        select(Payment)
        .where(
            Payment.id == payment_id,
            Payment.business_id == business_id,
        )
        .with_for_update()
    )
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    invoice = db.scalar(
        select(Invoice)
        .where(
            Invoice.id == payment.invoice_id,
            Invoice.business_id == business_id,
        )
        .with_for_update()
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated invoice not found.",
        )

    reversed_amount = payment.amount
    new_paid = round_money(max(Decimal("0.00"), invoice.amount_paid - reversed_amount))
    new_balance = round_money(max(Decimal("0.00"), invoice.total_amount - new_paid))

    invoice.amount_paid = new_paid
    invoice.balance_due = new_balance
    if invoice.status != "void":
        invoice.status = "issued" if new_paid == Decimal("0.00") else "partially_paid"
    invoice.pdf_storage_key = None
    invoice.pdf_generated_at = None

    db.delete(payment)

    record_invoice_modification(
        db,
        invoice=invoice,
        current_user=current_user,
        action="payment_reversed",
        summary=f"Reversed payment of {invoice.currency_code} {reversed_amount:.2f}.",
        changes={
            "amount_paid": str(new_paid),
            "balance_due": str(new_balance),
            "status": invoice.status,
        },
    )
    record_audit_event(
        db,
        business_id=business_id,
        user_id=current_user.id,
        action="payment.deleted",
        entity_type="payment",
        entity_id=payment_id,
        details={
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "amount": str(reversed_amount),
            "new_status": invoice.status,
        },
    )
    db.commit()
