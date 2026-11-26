"""FastAPI authentication, approval-gate, subscription, and admin authorization dependencies."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.business import Business
from app.models.saas import AdminSession, AdminUser
from app.models.session import UserSession
from app.models.user import User
from app.services.admin_service import get_active_admin_session
from app.services.auth_service import get_active_session_and_user
from app.services.saas_service import evaluate_business_subscription, get_saas_settings


def get_current_session_and_user(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[UserSession, User]:
    """Require a valid, unrevoked, unexpired user session cookie (allows pending/approved gate views)."""
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    resolved = get_active_session_and_user(db, raw_token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return resolved


def get_authenticated_user(
    resolved: tuple[UserSession, User] = Depends(get_current_session_and_user),
) -> User:
    """Return the authenticated User regardless of pending/subscription activation state."""
    return resolved[1]


def get_current_user(
    resolved: tuple[UserSession, User] = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
) -> User:
    """Require an approved, activated business user (blocks PENDING_APPROVAL & NOT_ACTIVATED).

    Allows EXPIRED users to read/export existing data while mutations use get_active_subscription_user.
    """
    user = resolved[1]
    business = user.business
    if business is not None:
        evaluate_business_subscription(db, business)

    if user.approval_status == "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending administrator approval.",
        )
    if user.approval_status == "APPROVED" and (
        business is None or business.subscription_status == "NOT_ACTIVATED"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription is not activated yet. Enter an activation code or contact administrator.",
        )
    if user.approval_status != "ACTIVE" or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Please contact administrator.",
        )
    if business is None or business.subscription_status in {"NOT_ACTIVATED", "SUSPENDED", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription is inactive or suspended. Please contact administrator.",
        )

    return user


def get_active_subscription_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Require an unexpired active subscription when policy enforces expiry restrictions."""
    business = current_user.business
    policy = get_saas_settings(db)
    if (
        policy.enforce_subscription_expiry
        and business is not None
        and business.subscription_status == "EXPIRED"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your subscription has expired. Renew with an activation code or contact "
                "administrator to continue creating and modifying records."
            ),
        )
    return current_user


def get_current_business(
    current_user: User = Depends(get_current_user),
) -> Business:
    """Return the Business scoped to the authenticated approved/active User."""
    return current_user.business


def get_admin_session_and_user(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[AdminSession, AdminUser]:
    """Require a valid, active admin session cookie (strictly separate from business users)."""
    settings = get_settings()
    raw_token = request.cookies.get(settings.admin_session_cookie_name)
    resolved = get_active_admin_session(db, raw_token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator authentication required.",
        )
    return resolved


def get_current_admin_basic(
    resolved: tuple[AdminSession, AdminUser] = Depends(get_admin_session_and_user),
) -> AdminUser:
    """Return authenticated AdminUser (allows initial forced password change)."""
    return resolved[1]


def get_current_admin(
    admin_user: AdminUser = Depends(get_current_admin_basic),
) -> AdminUser:
    """Require administrator whose initial forced password change is complete."""
    if admin_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial password change required before accessing admin dashboard.",
        )
    return admin_user
