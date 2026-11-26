"""SaaS subscription evaluation, countdown metrics, feature limits, and activation codes."""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.product import Product
from app.models.saas import (
    ActivationAttempt,
    ActivationCode,
    ActivationCodeActivation,
    Notification,
    SaasSettings,
    Subscription,
    SubscriptionHistory,
    SubscriptionPlan,
)
from app.models.user import User
from app.schemas.saas import PlanLimitsUsage, SubscriptionSummary, SupportContactResponse
from app.services.audit_service import record_audit_event

_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalize naive datetimes (such as SQLite test rows) to UTC-aware datetimes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hash_activation_code(code_value: str) -> str:
    """Compute canonical uppercase SHA-256 hash for an activation code."""
    normalized = code_value.strip().upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_cryptographic_code() -> str:
    """Generate an unpredictable RMX-XXXX-XXXX-XXXX code using secrets."""
    groups = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        for _ in range(3)
    ]
    return f"RMX-{groups[0]}-{groups[1]}-{groups[2]}"


def get_saas_settings(db: Session, settings: Settings | None = None) -> SaasSettings:
    """Fetch singleton SaaS policy row (id=1), lazily seeding defaults if missing."""
    active_settings = settings or get_settings()
    row = db.get(SaasSettings, 1)
    if row is not None:
        return row
    row = SaasSettings(
        id=1,
        enforce_subscription_expiry=active_settings.enforce_subscription_expiry,
        allow_self_activation=active_settings.allow_self_activation,
        notification_intervals_days=active_settings.notification_intervals_days,
        support_email=active_settings.support_email,
        support_phone=active_settings.support_phone,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_support_contact(db: Session) -> SupportContactResponse:
    active_settings = get_settings()
    try:
        row = get_saas_settings(db, active_settings)
        return SupportContactResponse(
            support_email=row.support_email,
            support_phone=row.support_phone,
            allow_self_activation=row.allow_self_activation,
            enforce_subscription_expiry=row.enforce_subscription_expiry,
        )
    except Exception:
        return SupportContactResponse(
            support_email=active_settings.support_email,
            support_phone=active_settings.support_phone,
            allow_self_activation=active_settings.allow_self_activation,
            enforce_subscription_expiry=active_settings.enforce_subscription_expiry,
        )


def parse_notification_intervals(raw: str | None) -> list[int]:
    intervals: list[int] = []
    for part in (raw or "30,15,7,3,1,0").split(","):
        cleaned = part.strip()
        if cleaned.isdigit():
            val = int(cleaned)
            if 0 <= val <= 365 and val not in intervals:
                intervals.append(val)
    return sorted(intervals, reverse=True) or [30, 15, 7, 3, 1, 0]


def get_latest_subscription(db: Session, business_id: int) -> Subscription | None:
    return db.scalar(
        select(Subscription)
        .options(joinedload(Subscription.plan))
        .where(Subscription.business_id == business_id)
        .order_by(Subscription.id.desc())
        .limit(1)
    )


def _create_notification_if_absent(
    db: Session,
    *,
    business_id: int | None,
    user_id: int | None,
    audience: str,
    category: str,
    severity: str,
    title: str,
    message: str,
    trigger_key: str,
) -> None:
    existing = db.scalar(select(Notification.id).where(Notification.trigger_key == trigger_key))
    if existing is not None:
        return
    db.add(
        Notification(
            business_id=business_id,
            user_id=user_id,
            audience=audience,
            category=category,
            severity=severity,
            title=title,
            message=message,
            trigger_key=trigger_key,
            is_read=False,
        )
    )


def evaluate_business_subscription(
    db: Session,
    business: Business,
    *,
    now: datetime | None = None,
) -> Subscription | None:
    """Evaluate active/expiry state on server UTC clock and trigger expiry notifications."""
    utc_now = as_utc(now or datetime.now(timezone.utc))
    assert utc_now is not None
    sub = get_latest_subscription(db, business.id)
    if sub is None:
        if business.subscription_status != "NOT_ACTIVATED":
            business.subscription_status = "NOT_ACTIVATED"
            db.commit()
        return None

    policy = get_saas_settings(db)
    expires_at = as_utc(sub.expires_at)
    mutated = False

    if sub.status == "ACTIVE" and expires_at is not None:
        if utc_now >= expires_at:
            sub.status = "EXPIRED"
            business.subscription_status = "EXPIRED"
            db.add(
                SubscriptionHistory(
                    subscription_id=sub.id,
                    business_id=business.id,
                    actor_type="system",
                    action="expired",
                    previous_status="ACTIVE",
                    new_status="EXPIRED",
                    previous_expires_at=expires_at,
                    new_expires_at=expires_at,
                    details_json={"reason": "Subscription expiry timestamp reached."},
                )
            )
            _create_notification_if_absent(
                db,
                business_id=business.id,
                user_id=None,
                audience="business",
                category="subscription_expiry",
                severity="error",
                title="Subscription Expired",
                message=f"Your {sub.plan_name} subscription expired on {expires_at.strftime('%d %b %Y UTC')}. Enter a renewal code or contact administrator.",
                trigger_key=f"sub:{sub.id}:exp:{int(expires_at.timestamp())}:day:0",
            )
            _create_notification_if_absent(
                db,
                business_id=business.id,
                user_id=None,
                audience="admin",
                category="subscription_expiry",
                severity="warning",
                title=f"Subscription Expired: {business.name}",
                message=f"Business '{business.name}' ({sub.plan_name}) has expired.",
                trigger_key=f"admin:sub:{sub.id}:exp:{int(expires_at.timestamp())}:day:0",
            )
            mutated = True
        else:
            remaining_days = max(0, int((expires_at - utc_now).total_seconds() // 86400))
            intervals = [d for d in parse_notification_intervals(policy.notification_intervals_days) if d > 0]
            for threshold in intervals:
                if remaining_days <= threshold:
                    severity = "warning" if threshold <= 7 else "info"
                    _create_notification_if_absent(
                        db,
                        business_id=business.id,
                        user_id=None,
                        audience="business",
                        category="subscription_expiry",
                        severity=severity,
                        title=f"Subscription Expiring Soon ({remaining_days}d remaining)",
                        message=(
                            f"Your {sub.plan_name} plan expires on "
                            f"{expires_at.strftime('%d %b %Y')} ({remaining_days} days remaining). "
                            "Contact administrator or activate a renewal code in advance."
                        ),
                        trigger_key=f"sub:{sub.id}:exp:{int(expires_at.timestamp())}:day:{threshold}",
                    )
                    mutated = True
                    break
    elif business.subscription_status != sub.status:
        business.subscription_status = sub.status
        mutated = True

    if mutated:
        db.commit()
        db.refresh(sub)
        db.refresh(business)

    return sub


def _compute_usage(db: Session, business_id: int) -> tuple[int, int, int, int]:
    invoices_used = db.scalar(select(func.count(Invoice.id)).where(Invoice.business_id == business_id)) or 0
    customers_used = (
        db.scalar(select(func.count(Customer.id)).where(Customer.business_id == business_id)) or 0
    )
    products_used = (
        db.scalar(select(func.count(Product.id)).where(Product.business_id == business_id)) or 0
    )
    users_used = db.scalar(select(func.count(User.id)).where(User.business_id == business_id)) or 1
    return invoices_used, customers_used, products_used, users_used


def build_subscription_summary(
    db: Session,
    *,
    business: Business,
    user: User | None = None,
) -> SubscriptionSummary:
    """Compute exact countdown, access flags, and plan limits for the authenticated business."""
    utc_now = datetime.now(timezone.utc)
    policy = get_saas_settings(db)
    sub = evaluate_business_subscription(db, business, now=utc_now)

    invoices_used, customers_used, products_used, users_used = _compute_usage(db, business.id)
    plan = sub.plan if sub is not None else None
    limits = PlanLimitsUsage(
        max_invoices=plan.max_invoices if plan else None,
        invoices_used=invoices_used,
        max_customers=plan.max_customers if plan else None,
        customers_used=customers_used,
        max_products=plan.max_products if plan else None,
        products_used=products_used,
        max_users=plan.max_users if plan else None,
        users_used=users_used,
        allow_reports=plan.allow_reports if plan else True,
        allow_pdf_export=plan.allow_pdf_export if plan else True,
        allow_custom_themes=plan.allow_custom_themes if plan else True,
    )

    approval_status = user.approval_status if user is not None else "ACTIVE"
    can_self_activate = bool(
        policy.allow_self_activation
        and (user is None or user.allow_self_activation)
        and approval_status in {"APPROVED", "ACTIVE"}
    )

    if sub is None:
        return SubscriptionSummary(
            status=business.subscription_status if business.subscription_status in {"NOT_ACTIVATED", "ACTIVE", "EXPIRED", "SUSPENDED", "CANCELLED"} else "NOT_ACTIVATED",  # type: ignore[arg-type]
            approval_status=approval_status,
            server_now=utc_now,
            can_access_dashboard=False,
            can_write_data=False,
            can_self_activate=can_self_activate,
            limits=limits,
        )

    starts_at = as_utc(sub.starts_at)
    expires_at = as_utc(sub.expires_at)

    total_seconds = 0
    remaining_seconds = 0
    remaining_days = 0
    remaining_hours = 0
    progress_percent = 0.0
    total_duration_days = 0

    if starts_at and expires_at and expires_at > starts_at:
        total_seconds = int((expires_at - starts_at).total_seconds())
        total_duration_days = max(1, int(round(total_seconds / 86400)))
        if sub.status == "ACTIVE" and expires_at > utc_now:
            remaining_seconds = max(0, int((expires_at - utc_now).total_seconds()))
            remaining_days = remaining_seconds // 86400
            remaining_hours = (remaining_seconds % 86400) // 3600
            progress_percent = round(min(100.0, max(0.0, (remaining_seconds / total_seconds) * 100.0)), 2)

    is_expired = sub.status == "EXPIRED"
    is_expiring_soon = sub.status == "ACTIVE" and remaining_days <= 7

    account_ok = approval_status == "ACTIVE" and (user is None or user.is_active)
    can_access_dashboard = account_ok and (
        sub.status == "ACTIVE" or (not policy.enforce_subscription_expiry and is_expired)
    )
    can_write_data = account_ok and (
        sub.status == "ACTIVE" or (not policy.enforce_subscription_expiry and is_expired)
    )

    return SubscriptionSummary(
        id=sub.id,
        plan_id=sub.plan_id,
        plan_name=sub.plan_name,
        status=sub.status,  # type: ignore[arg-type]
        approval_status=approval_status,
        starts_at=starts_at,
        expires_at=expires_at,
        server_now=utc_now,
        total_duration_days=total_duration_days,
        remaining_seconds=remaining_seconds,
        remaining_days=remaining_days,
        remaining_hours=remaining_hours,
        progress_percent=progress_percent,
        is_expiring_soon=is_expiring_soon,
        is_expired=is_expired,
        can_access_dashboard=can_access_dashboard,
        can_write_data=can_write_data,
        can_self_activate=can_self_activate,
        allow_export_when_expired=True,
        limits=limits,
    )


def enforce_plan_feature_limit(
    db: Session,
    *,
    business: Business,
    resource: str,
) -> None:
    """Enforce configurable subscription plan quotas or feature flags when creating resources."""
    sub = get_latest_subscription(db, business.id)
    if sub is None or sub.plan is None:
        return
    plan = sub.plan
    if resource == "invoices" and plan.max_invoices is not None:
        count = db.scalar(select(func.count(Invoice.id)).where(Invoice.business_id == business.id)) or 0
        if count >= plan.max_invoices:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Plan limit reached: '{plan.name}' allows up to {plan.max_invoices} invoices. Contact admin to upgrade.",
            )
    elif resource == "customers" and plan.max_customers is not None:
        count = db.scalar(select(func.count(Customer.id)).where(Customer.business_id == business.id)) or 0
        if count >= plan.max_customers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Plan limit reached: '{plan.name}' allows up to {plan.max_customers} customers. Contact admin to upgrade.",
            )
    elif resource == "products" and plan.max_products is not None:
        count = db.scalar(select(func.count(Product.id)).where(Product.business_id == business.id)) or 0
        if count >= plan.max_products:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Plan limit reached: '{plan.name}' allows up to {plan.max_products} products. Contact admin to upgrade.",
            )
    elif resource == "reports" and not plan.allow_reports:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Reports are disabled on your current '{plan.name}' subscription plan.",
        )
    elif resource == "pdf" and not plan.allow_pdf_export:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"PDF export is disabled on your current '{plan.name}' subscription plan.",
        )
    elif resource == "themes" and not plan.allow_custom_themes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Custom invoice themes are disabled on your current '{plan.name}' subscription plan.",
        )


def _check_activation_rate_limit(
    db: Session,
    *,
    actor_key: str,
    settings: Settings,
) -> None:
    window_start = datetime.now(timezone.utc) - timedelta(
        minutes=settings.activation_rate_limit_window_minutes
    )
    failed_count = (
        db.scalar(
            select(func.count(ActivationAttempt.id)).where(
                ActivationAttempt.actor_key == actor_key,
                ActivationAttempt.succeeded.is_(False),
                ActivationAttempt.created_at >= window_start,
            )
        )
        or 0
    )
    if failed_count >= settings.activation_rate_limit_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many invalid activation code attempts. Please wait a few minutes "
                "or contact the administrator."
            ),
        )


def _record_activation_attempt(db: Session, *, actor_key: str, succeeded: bool) -> None:
    db.add(ActivationAttempt(actor_key=actor_key, succeeded=succeeded))


def redeem_activation_code(
    db: Session,
    *,
    target_user: User,
    raw_code: str,
    initiated_by_admin_id: int | None = None,
    ip_address: str | None = None,
    extend_existing: bool = True,
    settings: Settings | None = None,
) -> tuple[Subscription, ActivationCode]:
    """Atomically redeem an activation code using row locking and strict security checks."""
    active_settings = settings or get_settings()
    policy = get_saas_settings(db, active_settings)
    utc_now = datetime.now(timezone.utc)

    # User must be approved first when redeeming self-service codes (never bypass admin approval!)
    if initiated_by_admin_id is None:
        if target_user.approval_status in {"PENDING_APPROVAL", "REJECTED"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account requires administrator approval before subscription activation.",
            )
        if not target_user.is_active or target_user.approval_status in {"INACTIVE", "SUSPENDED"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated or suspended. Contact administrator.",
            )
        if not policy.allow_self_activation or not target_user.allow_self_activation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-activation is disabled for your account. Contact administrator.",
            )

    actor_key = f"user:{target_user.id}"
    if initiated_by_admin_id is None:
        _check_activation_rate_limit(db, actor_key=actor_key, settings=active_settings)

    code_hash = hash_activation_code(raw_code)
    code_row = db.scalar(
        select(ActivationCode)
        .where(ActivationCode.code_hash == code_hash)
        .with_for_update()
    )

    if code_row is None:
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid activation code. Please check the code and try again.",
        )

    if code_row.status == "REVOKED" or code_row.revoked_at is not None:
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This activation code has been revoked by the administrator.",
        )

    code_exp = as_utc(code_row.expires_at)
    if code_exp is not None and utc_now >= code_exp:
        code_row.status = "EXPIRED"
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This activation code has expired.",
        )

    if not code_row.reusable and code_row.use_count >= 1:
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This activation code has already been redeemed.",
        )

    if code_row.reusable and code_row.use_count >= code_row.max_uses:
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This activation code has reached its maximum redemption limit.",
        )

    if code_row.assigned_user_id is not None and code_row.assigned_user_id != target_user.id:
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This activation code is assigned to another account.",
        )

    if (
        code_row.assigned_business_id is not None
        and code_row.assigned_business_id != target_user.business_id
    ):
        _record_activation_attempt(db, actor_key=actor_key, succeeded=False)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This activation code is assigned to another business.",
        )

    business = db.get(Business, target_user.business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")

    plan: SubscriptionPlan | None = (
        db.get(SubscriptionPlan, code_row.plan_id) if code_row.plan_id else None
    )
    plan_name = plan.name if plan else f"Standard {code_row.duration_days} Days"

    current_sub = db.scalar(
        select(Subscription)
        .where(Subscription.business_id == business.id)
        .order_by(Subscription.id.desc())
        .limit(1)
        .with_for_update()
    )

    prev_status = current_sub.status if current_sub else None
    prev_expires = as_utc(current_sub.expires_at) if current_sub else None
    is_extension = bool(
        extend_existing
        and current_sub is not None
        and current_sub.status == "ACTIVE"
        and prev_expires is not None
        and prev_expires > utc_now
    )

    if is_extension and current_sub is not None and prev_expires is not None:
        new_starts = as_utc(current_sub.starts_at) or utc_now
        new_expires = prev_expires + timedelta(days=code_row.duration_days)
        current_sub.expires_at = new_expires
        current_sub.status = "ACTIVE"
        if plan is not None:
            current_sub.plan_id = plan.id
            current_sub.plan_name = plan.name
        current_sub.activated_via_code_id = code_row.id
        sub_record = current_sub
        history_action = "extended"
    else:
        new_starts = utc_now
        new_expires = utc_now + timedelta(days=code_row.duration_days)
        sub_record = Subscription(
            business_id=business.id,
            plan_id=plan.id if plan else None,
            plan_name=plan_name,
            status="ACTIVE",
            starts_at=new_starts,
            expires_at=new_expires,
            assigned_by_admin_id=initiated_by_admin_id,
            activated_via_code_id=code_row.id,
            notes="Activated via activation code.",
        )
        db.add(sub_record)
        db.flush()
        history_action = "activated"

    code_row.use_count += 1
    code_row.activated_at = utc_now
    if not code_row.reusable or code_row.use_count >= code_row.max_uses:
        code_row.status = "ACTIVATED"

    business.subscription_status = "ACTIVE"
    if target_user.approval_status in {"APPROVED", "PENDING_APPROVAL"} and (
        initiated_by_admin_id is not None or target_user.approval_status == "APPROVED"
    ):
        target_user.approval_status = "ACTIVE"
        target_user.is_active = True
        if target_user.approved_at is None:
            target_user.approved_at = utc_now

    db.add(
        ActivationCodeActivation(
            activation_code_id=code_row.id,
            business_id=business.id,
            user_id=target_user.id,
            subscription_id=sub_record.id,
            action=history_action,
            ip_address=ip_address,
        )
    )
    db.add(
        SubscriptionHistory(
            subscription_id=sub_record.id,
            business_id=business.id,
            admin_user_id=initiated_by_admin_id,
            actor_type="admin" if initiated_by_admin_id is not None else "user",
            action=history_action,
            previous_status=prev_status,
            new_status="ACTIVE",
            previous_expires_at=prev_expires,
            new_expires_at=new_expires,
            details_json={"code_id": code_row.id, "duration_days": code_row.duration_days},
        )
    )
    db.add(
        Notification(
            business_id=business.id,
            user_id=target_user.id,
            audience="business",
            category="subscription_expiry",
            severity="success",
            title="Subscription Activated",
            message=(
                f"Your {sub_record.plan_name} subscription is now active until "
                f"{new_expires.strftime('%d %b %Y')}."
            ),
            is_read=False,
        )
    )
    _record_activation_attempt(db, actor_key=actor_key, succeeded=True)
    record_audit_event(
        db,
        business_id=business.id,
        user_id=target_user.id,
        action="subscription.activated",
        entity_type="subscription",
        entity_id=sub_record.id,
        details={"duration_days": code_row.duration_days, "action": history_action},
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent activation conflict occurred. Please retry.",
        ) from exc

    db.refresh(sub_record)
    db.refresh(code_row)
    return sub_record, code_row
