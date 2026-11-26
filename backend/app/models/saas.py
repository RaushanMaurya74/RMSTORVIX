"""SaaS Admin, Subscription Plan, Activation Code, History, Audit & Notification models."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AdminUser(Base):
    """Separate privileged administrator account for SaaS platform management."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="super_admin", server_default="super_admin"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["AdminSession"]] = relationship(
        "AdminSession", back_populates="admin_user", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    """Database-backed session for administrators using SHA-256 token hashes."""

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    admin_user: Mapped["AdminUser"] = relationship("AdminUser", back_populates="sessions")


class SubscriptionPlan(Base):
    """Configurable SaaS subscription plan with duration and feature limits."""

    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR", server_default="INR"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="ACTIVE", server_default="ACTIVE", index=True
    )

    # Configurable feature limits (null = unlimited)
    max_invoices: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_customers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_products: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_reports: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allow_pdf_export: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allow_custom_themes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Subscription(Base):
    """Business subscription record tracking lifecycle dates and status."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_business_status", "business_id", "status"),
        Index("ix_subscriptions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    plan_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="NOT_ACTIVATED", server_default="NOT_ACTIVATED"
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activated_via_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("activation_codes.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped["SubscriptionPlan | None"] = relationship("SubscriptionPlan")


class ActivationCode(Base):
    """Cryptographically generated subscription activation code."""

    __tablename__ = "activation_codes"
    __table_args__ = (
        Index("ix_activation_codes_status", "status"),
        Index("ix_activation_codes_assigned_user", "assigned_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_value: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    plan_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="GENERATED", server_default="GENERATED"
    )
    assigned_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_business_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
    )
    reusable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped["SubscriptionPlan | None"] = relationship("SubscriptionPlan")


class ActivationCodeActivation(Base):
    """Audit record of successful or attempted activation-code redemptions."""

    __tablename__ = "activation_code_activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activation_code_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("activation_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="activated")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class ActivationAttempt(Base):
    """Database-backed rate-limiting tracker for invalid activation code attempts."""

    __tablename__ = "activation_attempts"
    __table_args__ = (Index("ix_activation_attempts_actor_time", "actor_key", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_key: Mapped[str] = mapped_column(String(128), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserApprovalHistory(Base):
    """Immutable log of user approval/rejection/activation/suspension transitions."""

    __tablename__ = "user_approval_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class SubscriptionHistory(Base):
    """Immutable log of subscription assignments, extensions, expiries, and suspensions."""

    __tablename__ = "subscription_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False, default="admin")
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    new_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class AdminAuditLog(Base):
    """Immutable audit trail of all privileged administrator actions."""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (Index("ix_admin_audit_action_created", "action", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Notification(Base):
    """System & subscription expiry notifications for business users and administrators."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_audience_business", "audience", "business_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    audience: Mapped[str] = mapped_column(
        String(20), nullable=False, default="business", server_default="business"
    )
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="system", server_default="system"
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="info", server_default="info"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SaasSettings(Base):
    """Global SaaS subscription policy & support contact settings (row id=1)."""

    __tablename__ = "saas_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enforce_subscription_expiry: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allow_self_activation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notification_intervals_days: Mapped[str] = mapped_column(
        String(80), nullable=False, default="30,15,7,3,1,0", server_default="30,15,7,3,1,0"
    )
    support_email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        default="support@rmstorvix.com",
        server_default="support@rmstorvix.com",
    )
    support_phone: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="+91-1800-000-0000",
        server_default="+91-1800-000-0000",
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
