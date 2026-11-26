"""Authentication, registration approval workflow, and database-backed session lifecycle."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.models.business import Business
from app.models.saas import Notification, UserApprovalHistory
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import (
    ChangeUserPasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
)
from app.services.audit_service import record_audit_event
from app.services.gstin_service import verify_gstin_checksum
from app.services.saas_service import evaluate_business_subscription


def _as_utc(dt: datetime) -> datetime:
    """Normalize naive datetimes (e.g. from SQLite tests) to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _create_session_record(
    db: Session,
    *,
    user_id: int,
    settings: Settings,
    remember_me: bool = False,
) -> tuple[UserSession, str]:
    """Create a persistent UserSession storing only the SHA-256 token hash."""
    raw_token = generate_session_token()
    ttl_hours = 24 * 30 if remember_me else settings.session_ttl_hours
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    session_record = UserSession(
        user_id=user_id,
        token_hash=hash_session_token(raw_token),
        expires_at=expires_at,
    )
    db.add(session_record)
    return session_record, raw_token


def register_user_and_business(
    db: Session,
    payload: RegisterRequest,
    settings: Settings | None = None,
) -> tuple[User, Business, str]:
    """Register a SaaS business owner in PENDING_APPROVAL + NOT_ACTIVATED state."""
    active_settings = settings or get_settings()

    existing = db.scalar(select(User.id).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    cleaned_gstin = payload.gstin
    if cleaned_gstin and not verify_gstin_checksum(cleaned_gstin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provided GSTIN is invalid. Leave blank if not registered for GST.",
        )

    business = Business(
        name=payload.business_name,
        email=payload.email,
        phone=payload.phone,
        mobile=payload.phone,
        tax_id=cleaned_gstin,
        address_line1=payload.address,
        business_type=payload.business_type,
        subscription_status="NOT_ACTIVATED",
    )
    db.add(business)
    db.flush()

    user = User(
        business_id=business.id,
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role="owner",
        is_active=True,
        approval_status="PENDING_APPROVAL",
        allow_self_activation=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()

    db.add(
        UserApprovalHistory(
            user_id=user.id,
            business_id=business.id,
            previous_status=None,
            new_status="PENDING_APPROVAL",
            reason="Initial self-registration awaiting administrator approval.",
        )
    )
    db.add(
        Notification(
            business_id=None,
            user_id=user.id,
            audience="admin",
            category="approval",
            severity="info",
            title=f"New Registration: {business.name}",
            message=f"{user.full_name} ({user.email}) registered and is awaiting approval.",
            is_read=False,
        )
    )

    _, raw_token = _create_session_record(db, user_id=user.id, settings=active_settings)
    record_audit_event(
        db,
        business_id=business.id,
        user_id=user.id,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role, "approval_status": user.approval_status},
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        ) from exc

    db.refresh(user)
    db.refresh(business)
    return user, business, raw_token


def authenticate_user(
    db: Session,
    payload: LoginRequest,
    settings: Settings | None = None,
) -> tuple[User, Business, str]:
    """Authenticate user credentials and enforce approval/suspension status."""
    active_settings = settings or get_settings()

    user = db.scalar(
        select(User)
        .options(joinedload(User.business))
        .where(User.email == payload.email)
    )

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.approval_status == "REJECTED":
        reason = f" Reason: {user.rejection_reason}" if user.rejection_reason else ""
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your registration request was rejected.{reason} Contact administrator for details.",
        )

    if user.approval_status == "SUSPENDED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact the administrator.",
        )

    if not user.is_active or user.approval_status == "INACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is deactivated. Please contact the administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    if user.business is not None:
        evaluate_business_subscription(db, user.business)

    _, raw_token = _create_session_record(
        db,
        user_id=user.id,
        settings=active_settings,
        remember_me=payload.remember_me,
    )
    record_audit_event(
        db,
        business_id=user.business_id,
        user_id=user.id,
        action="user.logged_in",
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    db.refresh(user)

    return user, user.business, raw_token


def change_own_user_password(
    db: Session,
    *,
    user: User,
    payload: ChangeUserPasswordRequest,
) -> User:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    record_audit_event(
        db,
        business_id=user.business_id,
        user_id=user.id,
        action="user.password_changed",
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return user


def request_password_reset_notification(
    db: Session,
    payload: ForgotPasswordRequest,
) -> None:
    """Queue an admin password-reset notification without disclosing email existence."""
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        return

    db.add(
        Notification(
            business_id=None,
            user_id=user.id,
            audience="admin",
            category="approval",
            severity="warning",
            title=f"Password Reset Requested: {user.email}",
            message=(
                f"User {user.full_name} ({user.email}) requested a password reset."
                + (f" Note: {payload.reason}" if payload.reason else "")
            ),
            is_read=False,
        )
    )
    db.commit()


def get_active_session_and_user(
    db: Session,
    raw_token: str | None,
) -> tuple[UserSession, User] | None:
    """Resolve an active, unrevoked, unexpired session and its non-blocked user."""
    if not raw_token:
        return None

    token_hash = hash_session_token(raw_token)
    session_record = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user).joinedload(User.business))
        .where(UserSession.token_hash == token_hash)
    )

    if session_record is None or session_record.revoked_at is not None:
        return None

    if _as_utc(session_record.expires_at) <= datetime.now(timezone.utc):
        return None

    user = session_record.user
    if user is None or not user.is_active:
        return None
    if user.approval_status in {"INACTIVE", "SUSPENDED", "REJECTED"}:
        return None

    return session_record, user


def revoke_session(db: Session, raw_token: str | None) -> None:
    """Revoke an active session if present."""
    if not raw_token:
        return

    token_hash = hash_session_token(raw_token)
    session_record = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == token_hash)
    )
    if session_record is None or session_record.revoked_at is not None:
        return

    session_record.revoked_at = datetime.now(timezone.utc)
    if session_record.user is not None:
        record_audit_event(
            db,
            business_id=session_record.user.business_id,
            user_id=session_record.user.id,
            action="user.logged_out",
            entity_type="user_session",
            entity_id=session_record.id,
        )
    db.commit()
