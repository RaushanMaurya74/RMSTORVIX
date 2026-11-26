"""Add payments table.

Revision ID: 0004_payments
Revises: 0003_invoices_and_items
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_payments"
down_revision: str | Sequence[str] | None = "0003_invoices_and_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=40), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_payments_business_id", "payments", ["business_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_business_date", "payments", ["business_id", "payment_date"])
    op.create_index("ix_payments_business_invoice", "payments", ["business_id", "invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_business_invoice", table_name="payments")
    op.drop_index("ix_payments_business_date", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_business_id", table_name="payments")
    op.drop_table("payments")
