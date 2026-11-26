"""Add invoices and invoice_items tables.

Revision ID: 0003_invoices_and_items
Revises: 0002_customers_and_products
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_invoices_and_items"
down_revision: str | Sequence[str] | None = "0002_customers_and_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "tax_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "amount_paid",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("balance_due", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("pdf_storage_key", sa.String(length=255), nullable=True),
        sa.Column("pdf_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("business_id", "invoice_number", name="uq_invoices_business_number"),
    )
    op.create_index("ix_invoices_business_id", "invoices", ["business_id"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_business_status", "invoices", ["business_id", "status"])
    op.create_index("ix_invoices_business_issue_date", "invoices", ["business_id", "issue_date"])
    op.create_index("ix_invoices_business_customer", "invoices", ["business_id", "customer_id"])

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "discount_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "tax_rate",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("tax_label", sa.String(length=40), nullable=True),
        sa.Column("line_subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_discount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_tax", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
    )
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_items_invoice_id", table_name="invoice_items")
    op.drop_table("invoice_items")

    op.drop_index("ix_invoices_business_customer", table_name="invoices")
    op.drop_index("ix_invoices_business_issue_date", table_name="invoices")
    op.drop_index("ix_invoices_business_status", table_name="invoices")
    op.drop_index("ix_invoices_customer_id", table_name="invoices")
    op.drop_index("ix_invoices_business_id", table_name="invoices")
    op.drop_table("invoices")
