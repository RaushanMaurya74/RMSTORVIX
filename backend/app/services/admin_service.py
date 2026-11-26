"""Administrator authentication, dashboard metrics, user lifecycle, subscriptions, and code tools."""

import csv
from datetime import datetime, timedelta, timezone
import io

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.models.business import Business
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.saas import (
    ActivationCode,
    AdminAuditLog,
    AdminSession,
    AdminUser,
    Notification,
    SaasSettings,
    Subscription,
    SubscriptionHistory,
    SubscriptionPlan,
    UserApprovalHistory,
)
from app.models.user import User
from app.schemas.saas import (
    ActivationCodeAdminRedeemRequest,
    ActivationCodeGenerateRequest,
    ActivationCodeResponse,
    AdminOverviewStats,
    AdminPasswordChangeRequest,
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminSubscriptionRow,
    AdminSubscriptionStatusRequest,
    AdminUserBusinessEditRequest,
    AdminUserDetailResponse,
    AdminUserPasswordResetRequest,
    AdminUserRow,
    MonthlyRegistrationStat,
    SaasSettingsUpdate,
    StatusBreakdownItem,
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
)
from app.services.pagination import paginate_select
from app.services.saas_service import (
    as_utc,
    generate_cryptographic_code,
    get_latest_subscription,
    get_saas_settings,
    hash_activation_code,
    redeem_activation_code,
)


def record_admin_audit(
    db: Session,
    *,
    admin_user: AdminUser | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Append an immutable admin audit log entry (never recording passwords or activation secrets)."""
    db.add(
        AdminAuditLog(
            admin_user_id=admin_user.id if admin_user else None,
            actor_email=admin_user.email if admin_user else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details_json=details,
            ip_address=ip_address,
        )
    )


def authenticate_admin(
    db: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    settings: Settings | None = None,
) -> tuple[AdminUser, str]:
    active_settings = settings or get_settings()
    admin = db.scalar(select(AdminUser).where(AdminUser.email == email.strip().lower()))
    if admin is None or not verify_password(password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator email or password.",
        )
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator account is disabled.",
        )

    raw_token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=active_settings.admin_session_ttl_hours
    )
    db.add(
        AdminSession(
            admin_user_id=admin.id,
            token_hash=hash_session_token(raw_token),
            expires_at=expires_at,
        )
    )
    admin.last_login_at = datetime.now(timezone.utc)
    record_admin_audit(
        db,
        admin_user=admin,
        action="admin.logged_in",
        target_type="admin_user",
        target_id=admin.id,
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(admin)
    return admin, raw_token


def get_active_admin_session(
    db: Session,
    raw_token: str | None,
) -> tuple[AdminSession, AdminUser] | None:
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token)
    sess = db.scalar(
        select(AdminSession)
        .options(joinedload(AdminSession.admin_user))
        .where(AdminSession.token_hash == token_hash)
    )
    if sess is None or sess.revoked_at is not None:
        return None
    exp = as_utc(sess.expires_at)
    if exp is None or exp <= datetime.now(timezone.utc):
        return None
    if sess.admin_user is None or not sess.admin_user.is_active:
        return None
    return sess, sess.admin_user


def revoke_admin_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    token_hash = hash_session_token(raw_token)
    sess = db.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash))
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = datetime.now(timezone.utc)
        db.commit()


def change_admin_password(
    db: Session,
    *,
    admin: AdminUser,
    payload: AdminPasswordChangeRequest,
    ip_address: str | None = None,
) -> AdminUser:
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current administrator password is incorrect.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="New password and confirmation do not match.",
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="New password must be different from your initial/current password.",
        )

    admin.password_hash = hash_password(payload.new_password)
    admin.must_change_password = False
    record_admin_audit(
        db,
        admin_user=admin,
        action="admin.password_changed",
        target_type="admin_user",
        target_id=admin.id,
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(admin)
    return admin


def get_overview_stats(db: Session) -> AdminOverviewStats:
    """Compute real-time SaaS analytics directly from PostgreSQL tables."""
    utc_now = datetime.now(timezone.utc)
    soon_cutoff = utc_now + timedelta(days=7)

    # Sync expired active subscriptions so overview numbers match real clock
    active_subs = list(
        db.scalars(select(Subscription).where(Subscription.status == "ACTIVE")).all()
    )
    expired_any = False
    for sub in active_subs:
        exp = as_utc(sub.expires_at)
        if exp is not None and utc_now >= exp:
            sub.status = "EXPIRED"
            biz = db.get(Business, sub.business_id)
            if biz:
                biz.subscription_status = "EXPIRED"
            expired_any = True
    if expired_any:
        db.commit()

    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = (
        db.scalar(
            select(func.count(User.id)).where(
                User.approval_status == "ACTIVE", User.is_active.is_(True)
            )
        )
        or 0
    )
    pending_users = (
        db.scalar(
            select(func.count(User.id)).where(User.approval_status == "PENDING_APPROVAL")
        )
        or 0
    )
    deactivated_users = (
        db.scalar(
            select(func.count(User.id)).where(
                or_(User.approval_status == "INACTIVE", User.is_active.is_(False))
            )
        )
        or 0
    )
    suspended_users = (
        db.scalar(select(func.count(User.id)).where(User.approval_status == "SUSPENDED")) or 0
    )
    rejected_users = (
        db.scalar(select(func.count(User.id)).where(User.approval_status == "REJECTED")) or 0
    )

    active_subscriptions = (
        db.scalar(
            select(func.count(Business.id)).where(Business.subscription_status == "ACTIVE")
        )
        or 0
    )
    expired_subscriptions = (
        db.scalar(
            select(func.count(Business.id)).where(Business.subscription_status == "EXPIRED")
        )
        or 0
    )

    # Businesses whose active latest subscription expires within 7 days
    expiring_soon = (
        db.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.status == "ACTIVE",
                Subscription.expires_at.is_not(None),
                Subscription.expires_at > utc_now,
                Subscription.expires_at <= soon_cutoff,
            )
        )
        or 0
    )

    total_codes = db.scalar(select(func.count(ActivationCode.id))) or 0
    used_codes = (
        db.scalar(
            select(func.count(ActivationCode.id)).where(ActivationCode.status == "ACTIVATED")
        )
        or 0
    )
    available_codes = (
        db.scalar(
            select(func.count(ActivationCode.id)).where(
                ActivationCode.status.in_(["GENERATED", "AVAILABLE", "ASSIGNED"])
            )
        )
        or 0
    )

    # Monthly registrations across last 6 months (computed cleanly in Python across dialects)
    all_user_dates = list(db.scalars(select(User.created_at)).all())
    month_buckets: dict[str, int] = {}
    cursor = utc_now.replace(day=1)
    ordered_months: list[str] = []
    for offset in range(5, -1, -1):
        y = cursor.year
        m = cursor.month - offset
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y:04d}-{m:02d}"
        ordered_months.append(key)
        month_buckets[key] = 0
    for created in all_user_dates:
        dt = as_utc(created)
        if dt:
            k = dt.strftime("%Y-%m")
            if k in month_buckets:
                month_buckets[k] += 1
    monthly_stats = [
        MonthlyRegistrationStat(month=k, count=month_buckets[k]) for k in ordered_months
    ]

    sub_rows = db.execute(
        select(Business.subscription_status, func.count(Business.id)).group_by(
            Business.subscription_status
        )
    ).all()
    sub_breakdown = [StatusBreakdownItem(status=row[0], count=int(row[1])) for row in sub_rows]

    recent_audit = db.scalar(select(func.count(AdminAuditLog.id))) or 0

    return AdminOverviewStats(
        total_registered_users=int(total_users),
        active_users=int(active_users),
        pending_approval_users=int(pending_users),
        deactivated_users=int(deactivated_users),
        suspended_users=int(suspended_users),
        rejected_users=int(rejected_users),
        active_subscriptions=int(active_subscriptions),
        expired_subscriptions=int(expired_subscriptions),
        expiring_soon_subscriptions=int(expiring_soon),
        total_activation_codes=int(total_codes),
        used_activation_codes=int(used_codes),
        available_activation_codes=int(available_codes),
        monthly_registrations=monthly_stats,
        subscription_breakdown=sub_breakdown,
        recent_audit_count=int(recent_audit),
    )


def _serialize_admin_user_row(db: Session, user: User) -> AdminUserRow:
    biz = user.business
    sub = get_latest_subscription(db, biz.id) if biz else None
    utc_now = datetime.now(timezone.utc)
    remaining_days = 0
    exp = as_utc(sub.expires_at) if sub else None
    if sub and sub.status == "ACTIVE" and exp and exp > utc_now:
        remaining_days = max(0, int((exp - utc_now).total_seconds() // 86400))

    addr_parts = (
        [biz.address_line1, biz.city, biz.state] if biz else []
    )
    address_str = ", ".join(p for p in addr_parts if p) or None

    return AdminUserRow(
        id=user.id,
        business_id=user.business_id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone or (biz.mobile if biz else None),
        role=user.role,
        is_active=user.is_active,
        approval_status=user.approval_status,
        allow_self_activation=user.allow_self_activation,
        approved_at=user.approved_at,
        rejection_reason=user.rejection_reason,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        business_name=biz.name if biz else "—",
        business_type=biz.business_type if biz else None,
        business_gstin=biz.tax_id if biz else None,
        business_address=address_str,
        subscription_status=biz.subscription_status if biz else "NOT_ACTIVATED",
        subscription_plan_name=sub.plan_name if sub else None,
        subscription_expires_at=exp,
        subscription_remaining_days=remaining_days,
    )


def list_admin_users(
    db: Session,
    *,
    q: str | None = None,
    approval_status: str | None = None,
    subscription_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AdminUserRow], int, int]:
    stmt = select(User).join(Business, User.business_id == Business.id).options(joinedload(User.business))
    if approval_status and approval_status != "all":
        stmt = stmt.where(User.approval_status == approval_status)
    if subscription_status and subscription_status != "all":
        stmt = stmt.where(Business.subscription_status == subscription_status)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(term),
                User.full_name.ilike(term),
                Business.name.ilike(term),
                Business.tax_id.ilike(term),
            )
        )
    stmt = stmt.order_by(User.created_at.desc(), User.id.desc())
    items, total, total_pages = paginate_select(db, stmt, page=page, page_size=page_size)
    return [_serialize_admin_user_row(db, u) for u in items], total, total_pages


def _serialize_activation_code(
    db: Session,
    code: ActivationCode,
) -> ActivationCodeResponse:
    assigned_user = db.get(User, code.assigned_user_id) if code.assigned_user_id else None
    assigned_biz = (
        db.get(Business, code.assigned_business_id) if code.assigned_business_id else None
    )
    plan = db.get(SubscriptionPlan, code.plan_id) if code.plan_id else None
    return ActivationCodeResponse(
        id=code.id,
        code_value=code.code_value,
        plan_id=code.plan_id,
        plan_name=plan.name if plan else None,
        duration_days=code.duration_days,
        status=code.status,
        assigned_user_id=code.assigned_user_id,
        assigned_user_email=assigned_user.email if assigned_user else None,
        assigned_business_id=code.assigned_business_id,
        assigned_business_name=assigned_biz.name if assigned_biz else None,
        reusable=code.reusable,
        max_uses=code.max_uses,
        use_count=code.use_count,
        expires_at=as_utc(code.expires_at),
        activated_at=as_utc(code.activated_at),
        revoked_at=as_utc(code.revoked_at),
        notes=code.notes,
        created_at=code.created_at,
    )


def get_admin_user_detail(db: Session, user_id: int) -> AdminUserDetailResponse:
    user = db.scalar(
        select(User).options(joinedload(User.business)).where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    approval_hist = list(
        db.scalars(
            select(UserApprovalHistory)
            .where(UserApprovalHistory.user_id == user.id)
            .order_by(UserApprovalHistory.created_at.desc(), UserApprovalHistory.id.desc())
        ).all()
    )
    sub_hist = list(
        db.scalars(
            select(SubscriptionHistory)
            .where(SubscriptionHistory.business_id == user.business_id)
            .order_by(SubscriptionHistory.created_at.desc(), SubscriptionHistory.id.desc())
        ).all()
    )
    codes = list(
        db.scalars(
            select(ActivationCode)
            .where(ActivationCode.assigned_user_id == user.id)
            .order_by(ActivationCode.id.desc())
        ).all()
    )
    return AdminUserDetailResponse(
        user=_serialize_admin_user_row(db, user),
        approval_history=approval_hist,  # type: ignore[arg-type]
        subscription_history=sub_hist,  # type: ignore[arg-type]
        assigned_codes=[_serialize_activation_code(db, c) for c in codes],
    )


def _change_user_approval_status(
    db: Session,
    *,
    admin: AdminUser,
    user_id: int,
    new_status: str,
    is_active: bool,
    audit_action: str,
    reason: str | None = None,
    allow_self_activation: bool | None = None,
    ip_address: str | None = None,
) -> AdminUserRow:
    user = db.scalar(
        select(User).options(joinedload(User.business)).where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    prev = user.approval_status
    utc_now = datetime.now(timezone.utc)
    user.approval_status = new_status
    user.is_active = is_active
    if allow_self_activation is not None:
        user.allow_self_activation = allow_self_activation

    if new_status in {"APPROVED", "ACTIVE"}:
        user.approved_at = user.approved_at or utc_now
        user.approved_by_admin_id = admin.id
        user.rejection_reason = None
        user.rejected_at = None
    elif new_status == "REJECTED":
        user.rejected_at = utc_now
        user.rejection_reason = reason

    db.add(
        UserApprovalHistory(
            user_id=user.id,
            business_id=user.business_id,
            admin_user_id=admin.id,
            previous_status=prev,
            new_status=new_status,
            reason=reason,
        )
    )
    db.add(
        Notification(
            business_id=user.business_id,
            user_id=user.id,
            audience="business",
            category="approval",
            severity="success" if new_status in {"APPROVED", "ACTIVE"} else "warning",
            title=f"Account {new_status.replace('_', ' ').title()}",
            message=reason or f"Your account status was updated to {new_status}.",
            is_read=False,
        )
    )
    record_admin_audit(
        db,
        admin_user=admin,
        action=audit_action,
        target_type="user",
        target_id=user.id,
        details={"previous_status": prev, "new_status": new_status, "reason": reason},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(user)
    return _serialize_admin_user_row(db, user)


def approve_user_account(
    db: Session, *, admin: AdminUser, user_id: int, allow_self_activation: bool | None, reason: str | None, ip_address: str | None = None
) -> AdminUserRow:
    return _change_user_approval_status(
        db,
        admin=admin,
        user_id=user_id,
        new_status="APPROVED",
        is_active=True,
        audit_action="user.approved",
        reason=reason,
        allow_self_activation=allow_self_activation,
        ip_address=ip_address,
    )


def reject_user_account(
    db: Session, *, admin: AdminUser, user_id: int, reason: str | None, ip_address: str | None = None
) -> AdminUserRow:
    return _change_user_approval_status(
        db,
        admin=admin,
        user_id=user_id,
        new_status="REJECTED",
        is_active=False,
        audit_action="user.rejected",
        reason=reason,
        ip_address=ip_address,
    )


def activate_user_account(
    db: Session, *, admin: AdminUser, user_id: int, reason: str | None, ip_address: str | None = None
) -> AdminUserRow:
    return _change_user_approval_status(
        db,
        admin=admin,
        user_id=user_id,
        new_status="ACTIVE",
        is_active=True,
        audit_action="user.activated",
        reason=reason,
        ip_address=ip_address,
    )


def deactivate_user_account(
    db: Session, *, admin: AdminUser, user_id: int, reason: str | None, ip_address: str | None = None
) -> AdminUserRow:
    return _change_user_approval_status(
        db,
        admin=admin,
        user_id=user_id,
        new_status="INACTIVE",
        is_active=False,
        audit_action="user.deactivated",
        reason=reason,
        ip_address=ip_address,
    )


def suspend_user_account(
    db: Session, *, admin: AdminUser, user_id: int, reason: str | None, ip_address: str | None = None
) -> AdminUserRow:
    return _change_user_approval_status(
        db,
        admin=admin,
        user_id=user_id,
        new_status="SUSPENDED",
        is_active=False,
        audit_action="user.suspended",
        reason=reason,
        ip_address=ip_address,
    )


def reactivate_user_account(
    db: Session, *, admin: AdminUser, user_id: int, reason: str | None, ip_address: str | None = None
) -> AdminUserRow:
    return _change_user_approval_status(
        db,
        admin=admin,
        user_id=user_id,
        new_status="ACTIVE",
        is_active=True,
        audit_action="user.reactivated",
        reason=reason,
        ip_address=ip_address,
    )


def admin_edit_user_business(
    db: Session,
    *,
    admin: AdminUser,
    user_id: int,
    payload: AdminUserBusinessEditRequest,
    ip_address: str | None = None,
) -> AdminUserRow:
    user = db.scalar(
        select(User).options(joinedload(User.business)).where(User.id == user_id)
    )
    if user is None or user.business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.phone is not None:
        user.phone = payload.phone
        user.business.mobile = payload.phone
    if payload.allow_self_activation is not None:
        user.allow_self_activation = payload.allow_self_activation
    if payload.business_name is not None:
        user.business.name = payload.business_name
    if payload.business_type is not None:
        user.business.business_type = payload.business_type
    if payload.tax_id is not None:
        user.business.tax_id = payload.tax_id
    if payload.address_line1 is not None:
        user.business.address_line1 = payload.address_line1
    if payload.city is not None:
        user.business.city = payload.city
    if payload.state is not None:
        user.business.state = payload.state

    record_admin_audit(
        db,
        admin_user=admin,
        action="user.business_updated",
        target_type="user",
        target_id=user.id,
        details={"business_id": user.business_id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(user)
    return _serialize_admin_user_row(db, user)


def admin_reset_user_password(
    db: Session,
    *,
    admin: AdminUser,
    user_id: int,
    payload: AdminUserPasswordResetRequest,
    ip_address: str | None = None,
) -> AdminUserRow:
    user = db.scalar(
        select(User).options(joinedload(User.business)).where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = payload.require_password_change
    record_admin_audit(
        db,
        admin_user=admin,
        action="user.password_reset",
        target_type="user",
        target_id=user.id,
        details={"require_password_change": payload.require_password_change},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(user)
    return _serialize_admin_user_row(db, user)


def admin_delete_user(
    db: Session,
    *,
    admin: AdminUser,
    user_id: int,
    ip_address: str | None = None,
) -> None:
    """Delete an account only when no non-draft accounting records exist."""
    user = db.scalar(
        select(User).options(joinedload(User.business)).where(User.id == user_id)
    )
    if user is None or user.business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    finalized_count = (
        db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.business_id == user.business_id,
                Invoice.status != "draft",
            )
        )
        or 0
    )
    payment_count = (
        db.scalar(select(func.count(Payment.id)).where(Payment.business_id == user.business_id))
        or 0
    )
    if finalized_count > 0 or payment_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot permanently delete a business account with issued invoices or payment "
                "records. Deactivate or suspend the user instead."
            ),
        )

    target_email = user.email
    business = user.business
    db.delete(user)
    db.flush()
    remaining_owners = (
        db.scalar(select(func.count(User.id)).where(User.business_id == business.id)) or 0
    )
    if remaining_owners == 0:
        db.delete(business)

    record_admin_audit(
        db,
        admin_user=admin,
        action="user.deleted",
        target_type="user",
        target_id=user_id,
        details={"email": target_email},
        ip_address=ip_address,
    )
    db.commit()


# --- Plans ---
def list_plans(db: Session, *, include_inactive: bool = True) -> list[SubscriptionPlan]:
    stmt = select(SubscriptionPlan)
    if not include_inactive:
        stmt = stmt.where(SubscriptionPlan.status == "ACTIVE")
    stmt = stmt.order_by(SubscriptionPlan.duration_days.asc(), SubscriptionPlan.id.asc())
    return list(db.scalars(stmt).all())


def create_plan(
    db: Session, *, admin: AdminUser, payload: SubscriptionPlanCreate, ip_address: str | None = None
) -> SubscriptionPlan:
    existing = db.scalar(select(SubscriptionPlan.id).where(SubscriptionPlan.code == payload.code))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A subscription plan with this code already exists.",
        )
    plan = SubscriptionPlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    record_admin_audit(
        db,
        admin_user=admin,
        action="plan.created",
        target_type="subscription_plan",
        target_id=plan.id,
        details={"code": plan.code, "duration_days": plan.duration_days},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(
    db: Session,
    *,
    admin: AdminUser,
    plan_id: int,
    payload: SubscriptionPlanUpdate,
    ip_address: str | None = None,
) -> SubscriptionPlan:
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    dup = db.scalar(
        select(SubscriptionPlan.id).where(
            SubscriptionPlan.code == payload.code,
            SubscriptionPlan.id != plan_id,
        )
    )
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another plan already uses this code.",
        )

    for k, v in payload.model_dump().items():
        setattr(plan, k, v)
    record_admin_audit(
        db,
        admin_user=admin,
        action="plan.updated",
        target_type="subscription_plan",
        target_id=plan.id,
        details={"code": plan.code, "status": plan.status},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(plan)
    return plan


# --- Subscriptions ---
def _serialize_sub_row(db: Session, sub: Subscription) -> AdminSubscriptionRow:
    biz = db.get(Business, sub.business_id)
    owner = db.scalar(select(User).where(User.business_id == sub.business_id).limit(1))
    utc_now = datetime.now(timezone.utc)
    exp = as_utc(sub.expires_at)
    rem_days = 0
    if sub.status == "ACTIVE" and exp and exp > utc_now:
        rem_days = max(0, int((exp - utc_now).total_seconds() // 86400))
    return AdminSubscriptionRow(
        id=sub.id,
        business_id=sub.business_id,
        business_name=biz.name if biz else f"Business #{sub.business_id}",
        owner_email=owner.email if owner else None,
        owner_name=owner.full_name if owner else None,
        plan_id=sub.plan_id,
        plan_name=sub.plan_name,
        status=sub.status,
        starts_at=as_utc(sub.starts_at),
        expires_at=exp,
        remaining_days=rem_days,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def list_admin_subscriptions(
    db: Session,
    *,
    q: str | None = None,
    status_filter: str | None = None,
    plan_id: int | None = None,
    expiring_within_days: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AdminSubscriptionRow], int, int]:
    stmt = select(Subscription).join(Business, Subscription.business_id == Business.id)
    if status_filter and status_filter != "all":
        stmt = stmt.where(Subscription.status == status_filter)
    if plan_id is not None:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if expiring_within_days is not None:
        utc_now = datetime.now(timezone.utc)
        cutoff = utc_now + timedelta(days=expiring_within_days)
        stmt = stmt.where(
            Subscription.status == "ACTIVE",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > utc_now,
            Subscription.expires_at <= cutoff,
        )
    if q:
        term = f"%{q.strip()}%"
        owner_biz_ids = select(User.business_id).where(
            or_(User.email.ilike(term), User.full_name.ilike(term))
        )
        stmt = stmt.where(
            or_(
                Business.name.ilike(term),
                Subscription.plan_name.ilike(term),
                Business.id.in_(owner_biz_ids),
            )
        )
    stmt = stmt.order_by(Subscription.id.desc())
    items, total, total_pages = paginate_select(db, stmt, page=page, page_size=page_size)
    return [_serialize_sub_row(db, s) for s in items], total, total_pages


def assign_subscription_to_user(
    db: Session,
    *,
    admin: AdminUser,
    user_id: int,
    payload: AdminSubscriptionAssignRequest,
    ip_address: str | None = None,
) -> AdminSubscriptionRow:
    user = db.scalar(select(User).options(joinedload(User.business)).where(User.id == user_id))
    if user is None or user.business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    plan = db.get(SubscriptionPlan, payload.plan_id) if payload.plan_id else None
    if payload.plan_id and plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    duration_days = payload.duration_days or (plan.duration_days if plan else 30)
    plan_name = payload.plan_name or (plan.name if plan else f"Custom {duration_days} Days")

    utc_now = datetime.now(timezone.utc)
    expires_at = utc_now + timedelta(days=duration_days)
    prev_sub = get_latest_subscription(db, user.business_id)

    sub = Subscription(
        business_id=user.business_id,
        plan_id=plan.id if plan else None,
        plan_name=plan_name,
        status="ACTIVE",
        starts_at=utc_now,
        expires_at=expires_at,
        assigned_by_admin_id=admin.id,
        notes=payload.notes,
    )
    db.add(sub)
    db.flush()

    user.business.subscription_status = "ACTIVE"
    if payload.activate_user:
        prev_app = user.approval_status
        user.approval_status = "ACTIVE"
        user.is_active = True
        user.approved_at = user.approved_at or utc_now
        user.approved_by_admin_id = admin.id
        if prev_app != "ACTIVE":
            db.add(
                UserApprovalHistory(
                    user_id=user.id,
                    business_id=user.business_id,
                    admin_user_id=admin.id,
                    previous_status=prev_app,
                    new_status="ACTIVE",
                    reason="Activated along with subscription assignment.",
                )
            )

    db.add(
        SubscriptionHistory(
            subscription_id=sub.id,
            business_id=user.business_id,
            admin_user_id=admin.id,
            actor_type="admin",
            action="assigned",
            previous_status=prev_sub.status if prev_sub else None,
            new_status="ACTIVE",
            previous_expires_at=as_utc(prev_sub.expires_at) if prev_sub else None,
            new_expires_at=expires_at,
            details_json={"plan_name": plan_name, "duration_days": duration_days},
        )
    )
    record_admin_audit(
        db,
        admin_user=admin,
        action="subscription.assigned",
        target_type="subscription",
        target_id=sub.id,
        details={"user_id": user.id, "plan_name": plan_name, "duration_days": duration_days},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(sub)
    return _serialize_sub_row(db, sub)


def extend_subscription(
    db: Session,
    *,
    admin: AdminUser,
    subscription_id: int,
    payload: AdminSubscriptionExtendRequest,
    ip_address: str | None = None,
) -> AdminSubscriptionRow:
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")

    utc_now = datetime.now(timezone.utc)
    prev_exp = as_utc(sub.expires_at)
    base_time = prev_exp if (prev_exp is not None and prev_exp > utc_now) else utc_now
    new_exp = base_time + timedelta(days=payload.extra_days)

    prev_status = sub.status
    sub.starts_at = as_utc(sub.starts_at) or utc_now
    sub.expires_at = new_exp
    sub.status = "ACTIVE"
    if payload.notes:
        sub.notes = payload.notes

    biz = db.get(Business, sub.business_id)
    if biz:
        biz.subscription_status = "ACTIVE"

    db.add(
        SubscriptionHistory(
            subscription_id=sub.id,
            business_id=sub.business_id,
            admin_user_id=admin.id,
            actor_type="admin",
            action="extended",
            previous_status=prev_status,
            new_status="ACTIVE",
            previous_expires_at=prev_exp,
            new_expires_at=new_exp,
            details_json={"extra_days": payload.extra_days},
        )
    )
    record_admin_audit(
        db,
        admin_user=admin,
        action="subscription.extended",
        target_type="subscription",
        target_id=sub.id,
        details={"extra_days": payload.extra_days},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(sub)
    return _serialize_sub_row(db, sub)


def update_subscription_status(
    db: Session,
    *,
    admin: AdminUser,
    subscription_id: int,
    payload: AdminSubscriptionStatusRequest,
    ip_address: str | None = None,
) -> AdminSubscriptionRow:
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")

    prev_status = sub.status
    prev_exp = as_utc(sub.expires_at)
    utc_now = datetime.now(timezone.utc)

    sub.status = payload.status
    if payload.status == "EXPIRED":
        sub.expires_at = utc_now
    elif payload.status == "ACTIVE" and (prev_exp is None or prev_exp <= utc_now):
        sub.expires_at = utc_now + timedelta(days=30)
    if payload.notes:
        sub.notes = payload.notes

    biz = db.get(Business, sub.business_id)
    if biz:
        biz.subscription_status = payload.status

    db.add(
        SubscriptionHistory(
            subscription_id=sub.id,
            business_id=sub.business_id,
            admin_user_id=admin.id,
            actor_type="admin",
            action=payload.status.lower(),
            previous_status=prev_status,
            new_status=payload.status,
            previous_expires_at=prev_exp,
            new_expires_at=as_utc(sub.expires_at),
            details_json={"notes": payload.notes} if payload.notes else None,
        )
    )
    record_admin_audit(
        db,
        admin_user=admin,
        action=f"subscription.{payload.status.lower()}",
        target_type="subscription",
        target_id=sub.id,
        details={"previous_status": prev_status, "new_status": payload.status},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(sub)
    return _serialize_sub_row(db, sub)


# --- Activation Codes ---
def generate_activation_codes(
    db: Session,
    *,
    admin: AdminUser,
    payload: ActivationCodeGenerateRequest,
    ip_address: str | None = None,
) -> list[ActivationCodeResponse]:
    assigned_user = (
        db.get(User, payload.assigned_user_id) if payload.assigned_user_id else None
    )
    if payload.assigned_user_id and assigned_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found.")

    plan = db.get(SubscriptionPlan, payload.plan_id) if payload.plan_id else None
    if payload.plan_id and plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    utc_now = datetime.now(timezone.utc)
    code_exp = (
        utc_now + timedelta(days=payload.code_expires_in_days)
        if payload.code_expires_in_days
        else None
    )
    initial_status = "ASSIGNED" if assigned_user else "AVAILABLE"

    created_codes: list[ActivationCode] = []
    for _ in range(payload.count):
        candidate = generate_cryptographic_code()
        while db.scalar(select(ActivationCode.id).where(ActivationCode.code_value == candidate)) is not None:
            candidate = generate_cryptographic_code()

        row = ActivationCode(
            code_value=candidate,
            code_hash=hash_activation_code(candidate),
            plan_id=plan.id if plan else None,
            duration_days=payload.duration_days,
            status=initial_status,
            assigned_user_id=assigned_user.id if assigned_user else None,
            assigned_business_id=assigned_user.business_id if assigned_user else None,
            reusable=payload.reusable,
            max_uses=payload.max_uses if payload.reusable else 1,
            expires_at=code_exp,
            created_by_admin_id=admin.id,
            notes=payload.notes,
        )
        db.add(row)
        created_codes.append(row)

    db.flush()
    record_admin_audit(
        db,
        admin_user=admin,
        action="activation_code.generated",
        target_type="activation_code",
        target_id=created_codes[0].id if created_codes else None,
        details={
            "count": len(created_codes),
            "duration_days": payload.duration_days,
            "assigned_user_id": payload.assigned_user_id,
        },
        ip_address=ip_address,
    )
    db.commit()
    return [_serialize_activation_code(db, c) for c in created_codes]


def list_activation_codes(
    db: Session,
    *,
    q: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ActivationCodeResponse], int, int]:
    stmt = select(ActivationCode)
    if status_filter and status_filter != "all":
        stmt = stmt.where(ActivationCode.status == status_filter)
    if q:
        term = f"%{q.strip()}%"
        user_ids = select(User.id).where(or_(User.email.ilike(term), User.full_name.ilike(term)))
        stmt = stmt.where(
            or_(
                ActivationCode.code_value.ilike(term),
                ActivationCode.notes.ilike(term),
                ActivationCode.assigned_user_id.in_(user_ids),
            )
        )
    stmt = stmt.order_by(ActivationCode.id.desc())
    items, total, total_pages = paginate_select(db, stmt, page=page, page_size=page_size)
    return [_serialize_activation_code(db, c) for c in items], total, total_pages


def export_activation_codes_csv(db: Session, *, status_filter: str | None = None) -> str:
    stmt = select(ActivationCode).order_by(ActivationCode.id.desc())
    if status_filter and status_filter != "all":
        stmt = stmt.where(ActivationCode.status == status_filter)
    codes = [_serialize_activation_code(db, c) for c in db.scalars(stmt).all()]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Code",
            "Status",
            "Duration Days",
            "Plan",
            "Assigned User",
            "Assigned Business",
            "Use Count",
            "Activated At",
            "Expires At",
            "Created At",
        ]
    )
    for c in codes:
        writer.writerow(
            [
                c.id,
                c.code_value,
                c.status,
                c.duration_days,
                c.plan_name or "",
                c.assigned_user_email or "",
                c.assigned_business_name or "",
                f"{c.use_count}/{c.max_uses}",
                c.activated_at.isoformat() if c.activated_at else "",
                c.expires_at.isoformat() if c.expires_at else "",
                c.created_at.isoformat(),
            ]
        )
    return output.getvalue()


def assign_activation_code(
    db: Session,
    *,
    admin: AdminUser,
    code_id: int,
    user_id: int,
    ip_address: str | None = None,
) -> ActivationCodeResponse:
    code = db.get(ActivationCode, code_id)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activation code not found.")
    if code.status in {"REVOKED", "ACTIVATED", "EXPIRED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot assign an activation code in '{code.status}' state.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    code.assigned_user_id = user.id
    code.assigned_business_id = user.business_id
    code.status = "ASSIGNED"

    record_admin_audit(
        db,
        admin_user=admin,
        action="activation_code.assigned",
        target_type="activation_code",
        target_id=code.id,
        details={"assigned_user_id": user.id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(code)
    return _serialize_activation_code(db, code)


def revoke_activation_code(
    db: Session,
    *,
    admin: AdminUser,
    code_id: int,
    reason: str | None = None,
    ip_address: str | None = None,
) -> ActivationCodeResponse:
    code = db.get(ActivationCode, code_id)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activation code not found.")
    if code.status == "ACTIVATED" and not code.reusable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already-activated single-use codes cannot be revoked.",
        )
    if code.status == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Activation code is already revoked.",
        )

    code.status = "REVOKED"
    code.revoked_at = datetime.now(timezone.utc)
    code.revoked_by_admin_id = admin.id
    if reason:
        code.notes = f"Revoked: {reason}"

    record_admin_audit(
        db,
        admin_user=admin,
        action="activation_code.revoked",
        target_type="activation_code",
        target_id=code.id,
        details={"reason": reason},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(code)
    return _serialize_activation_code(db, code)


def admin_redeem_code_for_user(
    db: Session,
    *,
    admin: AdminUser,
    code_id: int,
    payload: ActivationCodeAdminRedeemRequest,
    ip_address: str | None = None,
) -> ActivationCodeResponse:
    code = db.get(ActivationCode, code_id)
    if code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activation code not found.")
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    sub, updated_code = redeem_activation_code(
        db,
        target_user=user,
        raw_code=code.code_value,
        initiated_by_admin_id=admin.id,
        ip_address=ip_address,
        extend_existing=payload.extend_existing,
    )
    record_admin_audit(
        db,
        admin_user=admin,
        action="activation_code.activated",
        target_type="activation_code",
        target_id=updated_code.id,
        details={"user_id": user.id, "subscription_id": sub.id},
        ip_address=ip_address,
    )
    db.commit()
    return _serialize_activation_code(db, updated_code)


def update_saas_settings(
    db: Session,
    *,
    admin: AdminUser,
    payload: SaasSettingsUpdate,
    ip_address: str | None = None,
) -> SaasSettings:
    row = get_saas_settings(db)
    row.enforce_subscription_expiry = payload.enforce_subscription_expiry
    row.allow_self_activation = payload.allow_self_activation
    row.notification_intervals_days = payload.notification_intervals_days
    row.support_email = payload.support_email
    row.support_phone = payload.support_phone
    row.updated_by_admin_id = admin.id

    record_admin_audit(
        db,
        admin_user=admin,
        action="saas_settings.updated",
        target_type="saas_settings",
        target_id=1,
        details=payload.model_dump(),
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(row)
    return row
