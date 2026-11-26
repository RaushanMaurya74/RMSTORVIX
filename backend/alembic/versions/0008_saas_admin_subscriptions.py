"""Add SaaS admin, subscription, activation code, audit, and notification schema.

Revision ID: 0008_saas_admin_subscriptions
Revises: 0007_logo_and_invoice_theme
Create Date: 2026-11-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_saas_admin_subscriptions"
down_revision: str | Sequence[str] | None = "0007_logo_and_invoice_theme"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="super_admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "admin_user_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_admin_sessions_admin_user_id", "admin_sessions", ["admin_user_id"])
    op.create_index("ix_admin_sessions_token_hash", "admin_sessions", ["token_hash"], unique=True)

    op.add_column("businesses", sa.Column("business_type", sa.String(length=80), nullable=True))
    op.add_column("businesses", sa.Column("mobile", sa.String(length=40), nullable=True))
    op.add_column(
        "businesses",
        sa.Column(
            "subscription_status",
            sa.String(length=24),
            nullable=False,
            server_default="NOT_ACTIVATED",
        ),
    )
    op.create_index("ix_businesses_subscription_status", "businesses", ["subscription_status"])

    op.add_column("users", sa.Column("phone", sa.String(length=40), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "approval_status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING_APPROVAL",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "allow_self_activation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "approved_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("users", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("rejection_reason", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_approval_status", "users", ["approval_status"])

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("max_invoices", sa.Integer(), nullable=True),
        sa.Column("max_customers", sa.Integer(), nullable=True),
        sa.Column("max_products", sa.Integer(), nullable=True),
        sa.Column("max_users", sa.Integer(), nullable=True),
        sa.Column("allow_reports", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_pdf_export", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_custom_themes", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_subscription_plans_code", "subscription_plans", ["code"], unique=True)
    op.create_index("ix_subscription_plans_status", "subscription_plans", ["status"])

    op.create_table(
        "activation_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_value", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="GENERATED"),
        sa.Column(
            "assigned_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reusable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "revoked_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_activation_codes_code_value", "activation_codes", ["code_value"], unique=True)
    op.create_index("ix_activation_codes_code_hash", "activation_codes", ["code_hash"], unique=True)
    op.create_index("ix_activation_codes_status", "activation_codes", ["status"])
    op.create_index("ix_activation_codes_assigned_user", "activation_codes", ["assigned_user_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("plan_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="NOT_ACTIVATED"
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assigned_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "activated_via_code_id",
            sa.Integer(),
            sa.ForeignKey("activation_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_subscriptions_business_id", "subscriptions", ["business_id"])
    op.create_index("ix_subscriptions_business_status", "subscriptions", ["business_id", "status"])
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])

    op.create_table(
        "activation_code_activations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activation_code_id",
            sa.Integer(),
            sa.ForeignKey("activation_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="activated"),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_activation_code_activations_code_id",
        "activation_code_activations",
        ["activation_code_id"],
    )
    op.create_index(
        "ix_activation_code_activations_business_id",
        "activation_code_activations",
        ["business_id"],
    )
    op.create_index(
        "ix_activation_code_activations_created_at",
        "activation_code_activations",
        ["created_at"],
    )

    op.create_table(
        "activation_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_key", sa.String(length=128), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_activation_attempts_actor_time", "activation_attempts", ["actor_key", "created_at"]
    )

    op.create_table(
        "user_approval_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "admin_user_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("previous_status", sa.String(length=24), nullable=True),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_approval_history_user_id", "user_approval_history", ["user_id"])
    op.create_index("ix_user_approval_history_business_id", "user_approval_history", ["business_id"])
    op.create_index("ix_user_approval_history_created_at", "user_approval_history", ["created_at"])

    op.create_table(
        "subscription_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "admin_user_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_type", sa.String(length=24), nullable=False, server_default="admin"),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=True),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("previous_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_subscription_history_subscription_id", "subscription_history", ["subscription_id"])
    op.create_index("ix_subscription_history_business_id", "subscription_history", ["business_id"])
    op.create_index("ix_subscription_history_created_at", "subscription_history", ["created_at"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "admin_user_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_admin_audit_logs_admin_user_id", "admin_audit_logs", ["admin_user_id"])
    op.create_index(
        "ix_admin_audit_action_created", "admin_audit_logs", ["action", "created_at"]
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("audience", sa.String(length=20), nullable=False, server_default="business"),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="system"),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("trigger_key", sa.String(length=120), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_notifications_business_id", "notifications", ["business_id"])
    op.create_index("ix_notifications_trigger_key", "notifications", ["trigger_key"], unique=True)
    op.create_index(
        "ix_notifications_audience_business",
        "notifications",
        ["audience", "business_id", "created_at"],
    )

    op.create_table(
        "saas_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "enforce_subscription_expiry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "allow_self_activation", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "notification_intervals_days",
            sa.String(length=80),
            nullable=False,
            server_default="30,15,7,3,1,0",
        ),
        sa.Column(
            "support_email",
            sa.String(length=254),
            nullable=False,
            server_default="support@rmstorvix.com",
        ),
        sa.Column(
            "support_phone",
            sa.String(length=40),
            nullable=False,
            server_default="+91-1800-000-0000",
        ),
        sa.Column(
            "updated_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Non-destructive backfill for pre-existing businesses & users, plus default SaaS plans/settings
    op.execute(
        """
        INSERT INTO saas_settings (id, enforce_subscription_expiry, allow_self_activation, notification_intervals_days, support_email, support_phone)
        VALUES (1, true, true, '30,15,7,3,1,0', 'support@rmstorvix.com', '+91-1800-000-0000')
        ON CONFLICT (id) DO NOTHING;
        """
    )

    op.execute(
        """
        INSERT INTO subscription_plans (code, name, description, duration_days, price, currency_code, status, max_invoices, max_customers, max_products, max_users, allow_reports, allow_pdf_export, allow_custom_themes)
        VALUES
          ('trial_7', 'Trial 7 Days', 'Short evaluation access for new businesses.', 7, 0.00, 'INR', 'ACTIVE', 25, 25, 25, 2, true, true, true),
          ('starter_30', 'Starter Monthly', 'Full GST billing and inventory for 30 days.', 30, 499.00, 'INR', 'ACTIVE', 250, 200, 300, 3, true, true, true),
          ('growth_90', 'Growth Quarterly', 'Quarterly billing plan with extended capacity.', 90, 1299.00, 'INR', 'ACTIVE', 1000, 1000, 1000, 5, true, true, true),
          ('business_180', 'Business Half-Year', '6-month commercial plan for scaling teams.', 180, 2399.00, 'INR', 'ACTIVE', 5000, 3000, 3000, 10, true, true, true),
          ('premium_365', 'Premium Annual', 'Full-year unlimited RMSTORVIX SaaS workspace.', 365, 3999.00, 'INR', 'ACTIVE', NULL, NULL, NULL, NULL, true, true, true)
        ON CONFLICT (code) DO NOTHING;
        """
    )

    op.execute(
        """
        UPDATE users
        SET approval_status = 'ACTIVE',
            approved_at = COALESCE(approved_at, created_at, NOW())
        WHERE approval_status = 'PENDING_APPROVAL';
        """
    )

    op.execute(
        """
        UPDATE businesses
        SET subscription_status = 'ACTIVE'
        WHERE subscription_status = 'NOT_ACTIVATED';
        """
    )

    op.execute(
        """
        INSERT INTO subscriptions (business_id, plan_id, plan_name, status, starts_at, expires_at, notes)
        SELECT b.id,
               (SELECT id FROM subscription_plans WHERE code = 'premium_365' LIMIT 1),
               'Premium Annual',
               'ACTIVE',
               NOW(),
               NOW() + INTERVAL '365 days',
               'Auto-migrated active subscription for pre-SaaS business account.'
        FROM businesses b
        WHERE NOT EXISTS (
            SELECT 1 FROM subscriptions s WHERE s.business_id = b.id
        );
        """
    )


def downgrade() -> None:
    op.drop_table("saas_settings")
    op.drop_index("ix_notifications_audience_business", table_name="notifications")
    op.drop_index("ix_notifications_trigger_key", table_name="notifications")
    op.drop_index("ix_notifications_business_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_admin_audit_action_created", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_subscription_history_created_at", table_name="subscription_history")
    op.drop_index("ix_subscription_history_business_id", table_name="subscription_history")
    op.drop_index("ix_subscription_history_subscription_id", table_name="subscription_history")
    op.drop_table("subscription_history")
    op.drop_index("ix_user_approval_history_created_at", table_name="user_approval_history")
    op.drop_index("ix_user_approval_history_business_id", table_name="user_approval_history")
    op.drop_index("ix_user_approval_history_user_id", table_name="user_approval_history")
    op.drop_table("user_approval_history")
    op.drop_index("ix_activation_attempts_actor_time", table_name="activation_attempts")
    op.drop_table("activation_attempts")
    op.drop_index(
        "ix_activation_code_activations_created_at", table_name="activation_code_activations"
    )
    op.drop_index(
        "ix_activation_code_activations_business_id", table_name="activation_code_activations"
    )
    op.drop_index(
        "ix_activation_code_activations_code_id", table_name="activation_code_activations"
    )
    op.drop_table("activation_code_activations")
    op.drop_index("ix_subscriptions_expires_at", table_name="subscriptions")
    op.drop_index("ix_subscriptions_business_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_business_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_activation_codes_assigned_user", table_name="activation_codes")
    op.drop_index("ix_activation_codes_status", table_name="activation_codes")
    op.drop_index("ix_activation_codes_code_hash", table_name="activation_codes")
    op.drop_index("ix_activation_codes_code_value", table_name="activation_codes")
    op.drop_table("activation_codes")
    op.drop_index("ix_subscription_plans_status", table_name="subscription_plans")
    op.drop_index("ix_subscription_plans_code", table_name="subscription_plans")
    op.drop_table("subscription_plans")
    op.drop_index("ix_users_approval_status", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "rejection_reason")
    op.drop_column("users", "rejected_at")
    op.drop_column("users", "approved_by_admin_id")
    op.drop_column("users", "approved_at")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "allow_self_activation")
    op.drop_column("users", "approval_status")
    op.drop_column("users", "phone")
    op.drop_index("ix_businesses_subscription_status", table_name="businesses")
    op.drop_column("businesses", "subscription_status")
    op.drop_column("businesses", "mobile")
    op.drop_column("businesses", "business_type")
    op.drop_index("ix_admin_sessions_token_hash", table_name="admin_sessions")
    op.drop_index("ix_admin_sessions_admin_user_id", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
