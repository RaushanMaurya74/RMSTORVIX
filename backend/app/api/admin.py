"""Protected Administrator Panel endpoints (/api/v1/admin/*)."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_admin, get_current_admin_basic
from app.db.session import get_db
from app.models.saas import AdminAuditLog, AdminUser, Notification
from app.schemas.saas import (
    ActivationCodeAdminRedeemRequest,
    ActivationCodeAssignRequest,
    ActivationCodeGenerateRequest,
    ActivationCodeListResponse,
    ActivationCodeResponse,
    ActivationCodeRevokeRequest,
    AdminAuditListResponse,
    AdminAuditLogResponse,
    AdminAuthResponse,
    AdminLoginRequest,
    AdminOverviewStats,
    AdminPasswordChangeRequest,
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminSubscriptionListResponse,
    AdminSubscriptionRow,
    AdminSubscriptionStatusRequest,
    AdminUserBusinessEditRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserPasswordResetRequest,
    AdminUserRow,
    AdminUserStatusActionRequest,
    AdminUserSummary,
    NotificationListResponse,
    NotificationResponse,
    SaasSettingsResponse,
    SaasSettingsUpdate,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
)
from app.services.admin_service import (
    activate_user_account,
    admin_delete_user,
    admin_edit_user_business,
    admin_redeem_code_for_user,
    admin_reset_user_password,
    approve_user_account,
    assign_activation_code,
    assign_subscription_to_user,
    authenticate_admin,
    change_admin_password,
    create_plan,
    deactivate_user_account,
    export_activation_codes_csv,
    extend_subscription,
    generate_activation_codes,
    get_admin_user_detail,
    get_overview_stats,
    list_activation_codes,
    list_admin_subscriptions,
    list_admin_users,
    list_plans,
    reactivate_user_account,
    reject_user_account,
    revoke_activation_code,
    revoke_admin_session,
    suspend_user_account,
    update_plan,
    update_saas_settings,
    update_subscription_status,
)
from app.services.pagination import paginate_select
from app.services.saas_service import get_saas_settings

router = APIRouter(prefix="/admin", tags=["SaaS Administrator Panel"])


def _set_admin_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.admin_session_cookie_name,
        value=raw_token,
        max_age=settings.admin_session_ttl_hours * 3600,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.effective_cookie_secure,
        path="/",
    )


def _clear_admin_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.admin_session_cookie_name,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.effective_cookie_secure,
        path="/",
    )


# --- Admin Auth ---
@router.post("/auth/login", response_model=AdminAuthResponse)
def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AdminAuthResponse:
    ip_addr = request.client.host if request.client else None
    admin, raw_token = authenticate_admin(
        db, email=payload.email, password=payload.password, ip_address=ip_addr
    )
    _set_admin_cookie(response, raw_token)
    return AdminAuthResponse(admin=AdminUserSummary.model_validate(admin))


@router.post("/auth/logout")
def admin_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    raw_token = request.cookies.get(settings.admin_session_cookie_name)
    revoke_admin_session(db, raw_token)
    _clear_admin_cookie(response)
    return {"status": "logged_out"}


@router.get("/auth/me", response_model=AdminAuthResponse)
def read_admin_me(admin: AdminUser = Depends(get_current_admin_basic)) -> AdminAuthResponse:
    return AdminAuthResponse(admin=AdminUserSummary.model_validate(admin))


@router.post("/auth/change-password", response_model=AdminAuthResponse)
def admin_change_password_route(
    payload: AdminPasswordChangeRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin_basic),
    db: Session = Depends(get_db),
) -> AdminAuthResponse:
    ip_addr = request.client.host if request.client else None
    updated = change_admin_password(db, admin=admin, payload=payload, ip_address=ip_addr)
    return AdminAuthResponse(admin=AdminUserSummary.model_validate(updated))


# --- Overview ---
@router.get("/overview", response_model=AdminOverviewStats)
def read_admin_overview(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminOverviewStats:
    return get_overview_stats(db)


# --- User Management ---
@router.get("/users", response_model=AdminUserListResponse)
def read_admin_users(
    q: str | None = Query(default=None, max_length=120),
    approval_status: str | None = Query(default=None),
    subscription_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    items, total, total_pages = list_admin_users(
        db,
        q=q,
        approval_status=approval_status,
        subscription_status=subscription_status,
        page=page,
        page_size=page_size,
    )
    return AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def read_admin_user_detail_route(
    user_id: int = Path(ge=1),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    return get_admin_user_detail(db, user_id)


@router.post("/users/{user_id}/approve", response_model=AdminUserRow)
def approve_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    payload: AdminUserStatusActionRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return approve_user_account(
        db,
        admin=admin,
        user_id=user_id,
        allow_self_activation=payload.allow_self_activation if payload else None,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.post("/users/{user_id}/reject", response_model=AdminUserRow)
def reject_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    payload: AdminUserStatusActionRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return reject_user_account(
        db,
        admin=admin,
        user_id=user_id,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.post("/users/{user_id}/activate", response_model=AdminUserRow)
def activate_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    payload: AdminUserStatusActionRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return activate_user_account(
        db,
        admin=admin,
        user_id=user_id,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.post("/users/{user_id}/deactivate", response_model=AdminUserRow)
def deactivate_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    payload: AdminUserStatusActionRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return deactivate_user_account(
        db,
        admin=admin,
        user_id=user_id,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.post("/users/{user_id}/suspend", response_model=AdminUserRow)
def suspend_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    payload: AdminUserStatusActionRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return suspend_user_account(
        db,
        admin=admin,
        user_id=user_id,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.post("/users/{user_id}/reactivate", response_model=AdminUserRow)
def reactivate_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    payload: AdminUserStatusActionRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return reactivate_user_account(
        db,
        admin=admin,
        user_id=user_id,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.put("/users/{user_id}/business", response_model=AdminUserRow)
def edit_user_business_route(
    payload: AdminUserBusinessEditRequest,
    request: Request,
    user_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return admin_edit_user_business(
        db, admin=admin, user_id=user_id, payload=payload, ip_address=ip_addr
    )


@router.post("/users/{user_id}/reset-password", response_model=AdminUserRow)
def reset_user_password_route(
    payload: AdminUserPasswordResetRequest,
    request: Request,
    user_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserRow:
    ip_addr = request.client.host if request.client else None
    return admin_reset_user_password(
        db, admin=admin, user_id=user_id, payload=payload, ip_address=ip_addr
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_route(
    request: Request,
    user_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Response:
    ip_addr = request.client.host if request.client else None
    admin_delete_user(db, admin=admin, user_id=user_id, ip_address=ip_addr)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Subscription Plans ---
@router.get("/plans", response_model=list[SubscriptionPlanResponse])
def read_admin_plans(
    include_inactive: bool = Query(default=True),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[SubscriptionPlanResponse]:
    return [
        SubscriptionPlanResponse.model_validate(p)
        for p in list_plans(db, include_inactive=include_inactive)
    ]


@router.post(
    "/plans",
    response_model=SubscriptionPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_plan(
    payload: SubscriptionPlanCreate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> SubscriptionPlanResponse:
    ip_addr = request.client.host if request.client else None
    plan = create_plan(db, admin=admin, payload=payload, ip_address=ip_addr)
    return SubscriptionPlanResponse.model_validate(plan)


@router.put("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
def update_admin_plan(
    payload: SubscriptionPlanUpdate,
    request: Request,
    plan_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> SubscriptionPlanResponse:
    ip_addr = request.client.host if request.client else None
    plan = update_plan(db, admin=admin, plan_id=plan_id, payload=payload, ip_address=ip_addr)
    return SubscriptionPlanResponse.model_validate(plan)


# --- Subscription Management ---
@router.get("/subscriptions", response_model=AdminSubscriptionListResponse)
def read_admin_subscriptions(
    q: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
    plan_id: int | None = Query(default=None, ge=1),
    expiring_within_days: int | None = Query(default=None, ge=1, le=365),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminSubscriptionListResponse:
    items, total, total_pages = list_admin_subscriptions(
        db,
        q=q,
        status_filter=status_filter,
        plan_id=plan_id,
        expiring_within_days=expiring_within_days,
        page=page,
        page_size=page_size,
    )
    return AdminSubscriptionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/users/{user_id}/subscription", response_model=AdminSubscriptionRow)
def assign_user_subscription_route(
    payload: AdminSubscriptionAssignRequest,
    request: Request,
    user_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminSubscriptionRow:
    ip_addr = request.client.host if request.client else None
    return assign_subscription_to_user(
        db, admin=admin, user_id=user_id, payload=payload, ip_address=ip_addr
    )


@router.post("/subscriptions/{subscription_id}/extend", response_model=AdminSubscriptionRow)
def extend_subscription_route(
    payload: AdminSubscriptionExtendRequest,
    request: Request,
    subscription_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminSubscriptionRow:
    ip_addr = request.client.host if request.client else None
    return extend_subscription(
        db, admin=admin, subscription_id=subscription_id, payload=payload, ip_address=ip_addr
    )


@router.put("/subscriptions/{subscription_id}/status", response_model=AdminSubscriptionRow)
def update_subscription_status_route(
    payload: AdminSubscriptionStatusRequest,
    request: Request,
    subscription_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminSubscriptionRow:
    ip_addr = request.client.host if request.client else None
    return update_subscription_status(
        db, admin=admin, subscription_id=subscription_id, payload=payload, ip_address=ip_addr
    )


# --- Activation Codes ---
@router.get("/activation-codes", response_model=ActivationCodeListResponse)
def read_activation_codes_route(
    q: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ActivationCodeListResponse:
    items, total, total_pages = list_activation_codes(
        db, q=q, status_filter=status_filter, page=page, page_size=page_size
    )
    return ActivationCodeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/activation-codes/export.csv")
def export_activation_codes_route(
    status_filter: str | None = Query(default=None, alias="status"),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Response:
    csv_text = export_activation_codes_csv(db, status_filter=status_filter)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="activation_codes.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/activation-codes",
    response_model=list[ActivationCodeResponse],
    status_code=status.HTTP_201_CREATED,
)
def generate_activation_codes_route(
    payload: ActivationCodeGenerateRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[ActivationCodeResponse]:
    ip_addr = request.client.host if request.client else None
    return generate_activation_codes(db, admin=admin, payload=payload, ip_address=ip_addr)


@router.post("/activation-codes/{code_id}/assign", response_model=ActivationCodeResponse)
def assign_activation_code_route(
    payload: ActivationCodeAssignRequest,
    request: Request,
    code_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ActivationCodeResponse:
    ip_addr = request.client.host if request.client else None
    return assign_activation_code(
        db, admin=admin, code_id=code_id, user_id=payload.user_id, ip_address=ip_addr
    )


@router.post("/activation-codes/{code_id}/revoke", response_model=ActivationCodeResponse)
def revoke_activation_code_route(
    request: Request,
    code_id: int = Path(ge=1),
    payload: ActivationCodeRevokeRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ActivationCodeResponse:
    ip_addr = request.client.host if request.client else None
    return revoke_activation_code(
        db,
        admin=admin,
        code_id=code_id,
        reason=payload.reason if payload else None,
        ip_address=ip_addr,
    )


@router.post("/activation-codes/{code_id}/activate", response_model=ActivationCodeResponse)
def admin_redeem_activation_code_route(
    payload: ActivationCodeAdminRedeemRequest,
    request: Request,
    code_id: int = Path(ge=1),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ActivationCodeResponse:
    ip_addr = request.client.host if request.client else None
    return admin_redeem_code_for_user(
        db, admin=admin, code_id=code_id, payload=payload, ip_address=ip_addr
    )


# --- Admin Notifications, Audit Logs & Global Settings ---
@router.get("/notifications", response_model=NotificationListResponse)
def read_admin_notifications(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    items = list(
        db.scalars(
            select(Notification)
            .where(Notification.audience == "admin")
            .order_by(desc(Notification.created_at), desc(Notification.id))
            .limit(60)
        ).all()
    )
    unread = sum(1 for item in items if not item.is_read)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        unread_count=unread,
    )


@router.post("/notifications/{notification_id}/read")
def mark_admin_notification_read(
    notification_id: int = Path(ge=1),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.audience == "admin",
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    row.is_read = True
    db.commit()
    return {"status": "read"}


@router.post("/notifications/read-all")
def mark_all_admin_notifications_read(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.execute(
        update(Notification)
        .where(Notification.audience == "admin", Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"status": "all_read"}


@router.get("/audit-logs", response_model=AdminAuditListResponse)
def read_admin_audit_logs(
    action: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=25, ge=1, le=100),
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminAuditListResponse:
    stmt = select(AdminAuditLog)
    if action:
        stmt = stmt.where(AdminAuditLog.action.ilike(f"%{action.strip()}%"))
    stmt = stmt.order_by(AdminAuditLog.id.desc())
    items, total, total_pages = paginate_select(db, stmt, page=page, page_size=page_size)
    return AdminAuditListResponse(
        items=[AdminAuditLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/settings", response_model=SaasSettingsResponse)
def read_saas_settings_route(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> SaasSettingsResponse:
    return SaasSettingsResponse.model_validate(get_saas_settings(db))


@router.put("/settings", response_model=SaasSettingsResponse)
def save_saas_settings_route(
    payload: SaasSettingsUpdate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> SaasSettingsResponse:
    ip_addr = request.client.host if request.client else None
    updated = update_saas_settings(db, admin=admin, payload=payload, ip_address=ip_addr)
    return SaasSettingsResponse.model_validate(updated)
