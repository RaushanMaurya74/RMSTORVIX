"""SaaS Subscription, Activation Code redemption, Support contact, and Business Notification routes."""

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy import desc, or_, select, update
from sqlalchemy.orm import Session

from app.core.deps import get_authenticated_user
from app.db.session import get_db
from app.models.saas import Notification
from app.models.user import User
from app.schemas.saas import (
    ActivateCodeUserRequest,
    NotificationListResponse,
    NotificationResponse,
    SubscriptionSummary,
    SupportContactResponse,
)
from app.services.saas_service import (
    build_subscription_summary,
    get_support_contact,
    redeem_activation_code,
)

router = APIRouter(tags=["SaaS Subscription & Notifications"])


@router.get(
    "/saas/support",
    response_model=SupportContactResponse,
    summary="Get administrator support contact and self-activation policy flags",
)
def read_saas_support(db: Session = Depends(get_db)) -> SupportContactResponse:
    """Return safe public SaaS support details (never exposing secrets)."""
    return get_support_contact(db)


@router.get(
    "/subscription",
    response_model=SubscriptionSummary,
    summary="Get the signed-in business's live subscription countdown and limits",
)
def read_subscription_status(
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> SubscriptionSummary:
    """Evaluate UTC expiry, generate threshold alerts, and return subscription status."""
    return build_subscription_summary(
        db, business=current_user.business, user=current_user
    )


@router.post(
    "/subscription/activate",
    response_model=SubscriptionSummary,
    summary="Activate or renew subscription using an activation code",
)
def activate_subscription_with_code(
    payload: ActivateCodeUserRequest,
    request: Request,
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> SubscriptionSummary:
    """Redeem an assigned or open activation code cleanly inside a transaction."""
    ip_addr = request.client.host if request.client else None
    redeem_activation_code(
        db,
        target_user=current_user,
        raw_code=payload.code,
        ip_address=ip_addr,
        extend_existing=True,
    )
    db.refresh(current_user)
    db.refresh(current_user.business)
    return build_subscription_summary(
        db, business=current_user.business, user=current_user
    )


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    summary="List subscription and account notifications for the signed-in business",
)
def list_business_notifications(
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    """Return business-scoped notifications including subscription expiry warnings."""
    build_subscription_summary(db, business=current_user.business, user=current_user)
    items = list(
        db.scalars(
            select(Notification)
            .where(
                Notification.audience == "business",
                Notification.business_id == current_user.business_id,
                or_(
                    Notification.user_id.is_(None),
                    Notification.user_id == current_user.id,
                ),
            )
            .order_by(desc(Notification.created_at), desc(Notification.id))
            .limit(40)
        ).all()
    )
    unread_count = sum(1 for item in items if not item.is_read)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        unread_count=unread_count,
    )


@router.post(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark a business notification as read",
)
def mark_business_notification_read(
    notification_id: int = Path(ge=1),
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.audience == "business",
            Notification.business_id == current_user.business_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    row.is_read = True
    db.commit()
    return {"status": "read"}


@router.post(
    "/notifications/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark all business notifications as read",
)
def mark_all_business_notifications_read(
    current_user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.execute(
        update(Notification)
        .where(
            Notification.audience == "business",
            Notification.business_id == current_user.business_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    db.commit()
    return {"status": "all_read"}
