"""Protected Payment recording, listing, and reversal routes."""

from datetime import date

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_active_subscription_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import (
    PaymentCreate,
    PaymentListResponse,
    PaymentMethodType,
    PaymentResponse,
)
from app.services.payment_service import (
    delete_payment,
    list_payments,
    record_payment,
    serialize_payment,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List payments for the authenticated business",
)
def read_payments(
    q: str | None = Query(default=None, max_length=120),
    invoice_id: int | None = Query(default=None, ge=1),
    payment_method: PaymentMethodType | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentListResponse:
    """List recorded payments scoped to the signed-in business."""
    items, total, total_pages = list_payments(
        db,
        business_id=current_user.business_id,
        q=q,
        invoice_id=invoice_id,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return PaymentListResponse(
        items=[serialize_payment(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a payment against an issued invoice",
)
def create_payment_route(
    payload: PaymentCreate,
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    """Record a payment and recalculate invoice balance and status."""
    payment = record_payment(db, current_user=current_user, payload=payload)
    return serialize_payment(payment)


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reverse/delete a payment entry",
)
def delete_payment_route(
    payment_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a payment owned by the business and restore invoice balance."""
    delete_payment(db, current_user=current_user, payment_id=payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
