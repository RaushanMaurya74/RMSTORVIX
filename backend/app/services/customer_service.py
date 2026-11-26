"""Customer CRUD service scoped strictly to the authenticated business."""

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.audit_service import record_audit_event
from app.services.pagination import paginate_select


def get_owned_customer(db: Session, *, business_id: int, customer_id: int) -> Customer:
    """Fetch a customer only if owned by the caller's business; otherwise raise 404."""
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.business_id == business_id,
        )
    )
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )
    return customer


def list_customers(
    db: Session,
    *,
    business_id: int,
    q: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Customer], int, int]:
    """List customers owned by the business with optional search, filter, and pagination."""
    stmt = select(Customer).where(Customer.business_id == business_id)

    if is_active is not None:
        stmt = stmt.where(Customer.is_active.is_(is_active))

    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(term),
                Customer.company_name.ilike(term),
                Customer.email.ilike(term),
                Customer.phone.ilike(term),
            )
        )

    stmt = stmt.order_by(Customer.name.asc(), Customer.id.asc())
    return paginate_select(db, stmt, page=page, page_size=page_size)


def create_customer(
    db: Session,
    *,
    current_user: User,
    payload: CustomerCreate,
) -> Customer:
    """Create a customer within the authenticated business and record an audit event."""
    customer = Customer(
        business_id=current_user.business_id,
        **payload.model_dump(),
    )
    db.add(customer)
    db.flush()

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="customer.created",
        entity_type="customer",
        entity_id=customer.id,
        details={"name": customer.name},
    )
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(
    db: Session,
    *,
    current_user: User,
    customer_id: int,
    payload: CustomerUpdate,
) -> Customer:
    """Update an owned customer record and append an audit event."""
    customer = get_owned_customer(
        db, business_id=current_user.business_id, customer_id=customer_id
    )
    update_data = payload.model_dump()
    changed_fields = [
        field for field, value in update_data.items() if getattr(customer, field) != value
    ]
    for field, value in update_data.items():
        setattr(customer, field, value)

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="customer.updated",
        entity_type="customer",
        entity_id=customer.id,
        details={"changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(
    db: Session,
    *,
    current_user: User,
    customer_id: int,
) -> None:
    """Delete an owned customer record when no invoices reference it."""
    customer = get_owned_customer(
        db, business_id=current_user.business_id, customer_id=customer_id
    )
    has_invoice = db.scalar(
        select(Invoice.id).where(
            Invoice.business_id == current_user.business_id,
            Invoice.customer_id == customer_id,
        )
    )
    if has_invoice is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a customer with existing invoices. Mark the customer inactive instead.",
        )

    customer_name = customer.name
    db.delete(customer)

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="customer.deleted",
        entity_type="customer",
        entity_id=customer_id,
        details={"name": customer_name},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a customer with existing invoices. Mark the customer inactive instead.",
        ) from exc
