"""Pydantic schemas for SaaS subscriptions, plans, activation codes, admin panel, and notifications."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import CurrencyCode, NormalizedEmail, OptionalCleanText

ApprovalStatusType = Literal[
    "PENDING_APPROVAL",
    "APPROVED",
    "ACTIVE",
    "INACTIVE",
    "SUSPENDED",
    "REJECTED",
]

SubscriptionStatusType = Literal[
    "NOT_ACTIVATED",
    "ACTIVE",
    "EXPIRED",
    "SUSPENDED",
    "CANCELLED",
]

ActivationCodeStatusType = Literal[
    "GENERATED",
    "AVAILABLE",
    "ASSIGNED",
    "ACTIVATED",
    "EXPIRED",
    "REVOKED",
]


class SupportContactResponse(BaseModel):
    """Public/authenticated administrator contact metadata."""

    support_email: str
    support_phone: str
    allow_self_activation: bool
    enforce_subscription_expiry: bool


class PlanLimitsUsage(BaseModel):
    """Feature limits from the active plan paired with current business usage."""

    max_invoices: int | None = None
    invoices_used: int = 0
    max_customers: int | None = None
    customers_used: int = 0
    max_products: int | None = None
    products_used: int = 0
    max_users: int | None = None
    users_used: int = 1
    allow_reports: bool = True
    allow_pdf_export: bool = True
    allow_custom_themes: bool = True


class SubscriptionSummary(BaseModel):
    """Live business subscription status, countdown metadata, and feature limits."""

    id: int | None = None
    plan_id: int | None = None
    plan_name: str = "Not Activated"
    status: SubscriptionStatusType = "NOT_ACTIVATED"
    approval_status: str = "PENDING_APPROVAL"
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    server_now: datetime
    total_duration_days: int = 0
    remaining_seconds: int = 0
    remaining_days: int = 0
    remaining_hours: int = 0
    progress_percent: float = 0.0
    is_expiring_soon: bool = False
    is_expired: bool = False
    can_access_dashboard: bool = False
    can_write_data: bool = False
    can_self_activate: bool = False
    allow_export_when_expired: bool = True
    limits: PlanLimitsUsage = Field(default_factory=PlanLimitsUsage)


class ActivateCodeUserRequest(BaseModel):
    """Payload to activate or extend a business subscription using an activation code."""

    code: str = Field(min_length=6, max_length=32)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) < 6:
            raise ValueError("Enter a valid activation code.")
        return cleaned


class NotificationResponse(BaseModel):
    """Serialized SaaS or subscription expiry notification."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int | None = None
    user_id: int | None = None
    audience: str
    category: str
    severity: str
    title: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """List of notifications with unread count."""

    items: list[NotificationResponse]
    unread_count: int


# --- Admin Auth & Profile ---
class AdminLoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)


class AdminPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime


class AdminAuthResponse(BaseModel):
    admin: AdminUserSummary


# --- Admin Overview & Analytics ---
class MonthlyRegistrationStat(BaseModel):
    month: str
    count: int


class StatusBreakdownItem(BaseModel):
    status: str
    count: int


class AdminOverviewStats(BaseModel):
    total_registered_users: int
    active_users: int
    pending_approval_users: int
    deactivated_users: int
    suspended_users: int
    rejected_users: int
    active_subscriptions: int
    expired_subscriptions: int
    expiring_soon_subscriptions: int
    total_activation_codes: int
    used_activation_codes: int
    available_activation_codes: int
    monthly_registrations: list[MonthlyRegistrationStat]
    subscription_breakdown: list[StatusBreakdownItem]
    recent_audit_count: int = 0


# --- Admin Plan Management ---
class SubscriptionPlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=120)
    description: OptionalCleanText = Field(default=None, max_length=500)
    duration_days: int = Field(ge=1, le=3650)
    price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), le=Decimal("9999999.99"))
    currency_code: CurrencyCode = Field(default="INR")
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    max_invoices: int | None = Field(default=None, ge=1)
    max_customers: int | None = Field(default=None, ge=1)
    max_products: int | None = Field(default=None, ge=1)
    max_users: int | None = Field(default=None, ge=1)
    allow_reports: bool = True
    allow_pdf_export: bool = True
    allow_custom_themes: bool = True

    @field_validator("code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        cleaned = value.strip().lower().replace(" ", "_")
        if len(cleaned) < 2:
            raise ValueError("Plan code must be at least 2 characters.")
        return cleaned


class SubscriptionPlanUpdate(SubscriptionPlanCreate):
    pass


class SubscriptionPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None = None
    duration_days: int
    price: Decimal
    currency_code: str
    status: str
    max_invoices: int | None = None
    max_customers: int | None = None
    max_products: int | None = None
    max_users: int | None = None
    allow_reports: bool
    allow_pdf_export: bool
    allow_custom_themes: bool
    created_at: datetime
    updated_at: datetime


# --- Admin User & Business Management ---
class AdminUserRow(BaseModel):
    id: int
    business_id: int
    email: str
    full_name: str
    phone: str | None = None
    role: str
    is_active: bool
    approval_status: str
    allow_self_activation: bool
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    business_name: str
    business_type: str | None = None
    business_gstin: str | None = None
    business_address: str | None = None
    subscription_status: str
    subscription_plan_name: str | None = None
    subscription_expires_at: datetime | None = None
    subscription_remaining_days: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserApprovalHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    business_id: int
    admin_user_id: int | None = None
    previous_status: str | None = None
    new_status: str
    reason: str | None = None
    created_at: datetime


class SubscriptionHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int | None = None
    business_id: int
    admin_user_id: int | None = None
    actor_type: str
    action: str
    previous_status: str | None = None
    new_status: str
    previous_expires_at: datetime | None = None
    new_expires_at: datetime | None = None
    details_json: dict[str, Any] | None = None
    created_at: datetime


class AdminUserDetailResponse(BaseModel):
    user: AdminUserRow
    approval_history: list[UserApprovalHistoryResponse]
    subscription_history: list[SubscriptionHistoryResponse]
    assigned_codes: list["ActivationCodeResponse"]


class AdminUserStatusActionRequest(BaseModel):
    reason: OptionalCleanText = Field(default=None, max_length=500)
    allow_self_activation: bool | None = None


class AdminUserBusinessEditRequest(BaseModel):
    full_name: OptionalCleanText = Field(default=None, max_length=160)
    phone: OptionalCleanText = Field(default=None, max_length=40)
    allow_self_activation: bool | None = None
    business_name: OptionalCleanText = Field(default=None, max_length=160)
    business_type: OptionalCleanText = Field(default=None, max_length=80)
    tax_id: OptionalCleanText = Field(default=None, max_length=64)
    address_line1: OptionalCleanText = Field(default=None, max_length=200)
    city: OptionalCleanText = Field(default=None, max_length=100)
    state: OptionalCleanText = Field(default=None, max_length=100)


class AdminUserPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)
    require_password_change: bool = True


# --- Admin Subscriptions & Codes ---
class AdminSubscriptionAssignRequest(BaseModel):
    plan_id: int | None = Field(default=None, ge=1)
    plan_name: OptionalCleanText = Field(default=None, max_length=120)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    activate_user: bool = True
    notes: OptionalCleanText = Field(default=None, max_length=500)


class AdminSubscriptionExtendRequest(BaseModel):
    extra_days: int = Field(ge=1, le=3650)
    notes: OptionalCleanText = Field(default=None, max_length=500)


class AdminSubscriptionStatusRequest(BaseModel):
    status: Literal["ACTIVE", "EXPIRED", "SUSPENDED", "CANCELLED"]
    notes: OptionalCleanText = Field(default=None, max_length=500)


class AdminSubscriptionRow(BaseModel):
    id: int
    business_id: int
    business_name: str
    owner_email: str | None = None
    owner_name: str | None = None
    plan_id: int | None = None
    plan_name: str
    status: str
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    remaining_days: int = 0
    created_at: datetime
    updated_at: datetime


class AdminSubscriptionListResponse(BaseModel):
    items: list[AdminSubscriptionRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class ActivationCodeGenerateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    duration_days: int = Field(default=30, ge=1, le=3650)
    plan_id: int | None = Field(default=None, ge=1)
    assigned_user_id: int | None = Field(default=None, ge=1)
    reusable: bool = False
    max_uses: int = Field(default=1, ge=1, le=100)
    code_expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    notes: OptionalCleanText = Field(default=None, max_length=500)


class ActivationCodeAssignRequest(BaseModel):
    user_id: int = Field(ge=1)


class ActivationCodeRevokeRequest(BaseModel):
    reason: OptionalCleanText = Field(default=None, max_length=500)


class ActivationCodeAdminRedeemRequest(BaseModel):
    user_id: int = Field(ge=1)
    extend_existing: bool = True


class ActivationCodeResponse(BaseModel):
    id: int
    code_value: str
    plan_id: int | None = None
    plan_name: str | None = None
    duration_days: int
    status: str
    assigned_user_id: int | None = None
    assigned_user_email: str | None = None
    assigned_business_id: int | None = None
    assigned_business_name: str | None = None
    reusable: bool
    max_uses: int
    use_count: int
    expires_at: datetime | None = None
    activated_at: datetime | None = None
    revoked_at: datetime | None = None
    notes: str | None = None
    created_at: datetime


class ActivationCodeListResponse(BaseModel):
    items: list[ActivationCodeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_user_id: int | None = None
    actor_email: str | None = None
    action: str
    target_type: str
    target_id: int | None = None
    details_json: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime


class AdminAuditListResponse(BaseModel):
    items: list[AdminAuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SaasSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    enforce_subscription_expiry: bool
    allow_self_activation: bool
    notification_intervals_days: str
    support_email: str
    support_phone: str
    updated_at: datetime | None = None


class SaasSettingsUpdate(BaseModel):
    enforce_subscription_expiry: bool = True
    allow_self_activation: bool = True
    notification_intervals_days: str = Field(default="30,15,7,3,1,0", max_length=80)
    support_email: NormalizedEmail
    support_phone: str = Field(min_length=4, max_length=40)

    @field_validator("notification_intervals_days")
    @classmethod
    def validate_intervals(cls, value: str) -> str:
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            raise ValueError("Specify at least one day interval (e.g. 30,15,7,3,1,0).")
        cleaned: list[int] = []
        for p in parts:
            num = int(p)
            if num < 0 or num > 365:
                raise ValueError("Notification interval days must be between 0 and 365.")
            if num not in cleaned:
                cleaned.append(num)
        cleaned.sort(reverse=True)
        return ",".join(str(x) for x in cleaned)
