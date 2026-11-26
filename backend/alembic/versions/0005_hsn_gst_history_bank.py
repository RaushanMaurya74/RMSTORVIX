"""Add HSN/pricing/stock to products, GST split & history to invoices, and bank/UPI to businesses.

Revision ID: 0005_hsn_gst_history_bank
Revises: 0004_payments
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_hsn_gst_history_bank"
down_revision: str | Sequence[str] | None = "0004_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Feature 3: Business bank & UPI settings
    op.add_column("businesses", sa.Column("bank_account_holder", sa.String(length=160), nullable=True))
    op.add_column("businesses", sa.Column("bank_name", sa.String(length=160), nullable=True))
    op.add_column("businesses", sa.Column("bank_account_number", sa.String(length=64), nullable=True))
    op.add_column("businesses", sa.Column("bank_ifsc_code", sa.String(length=32), nullable=True))
    op.add_column("businesses", sa.Column("bank_branch", sa.String(length=160), nullable=True))
    op.add_column("businesses", sa.Column("upi_id", sa.String(length=120), nullable=True))

    # Feature 2: Product HSN, purchase price, stock quantity
    op.add_column("products", sa.Column("hsn_code", sa.String(length=16), nullable=True))
    op.add_column("products", sa.Column("purchase_price", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column(
        "products",
        sa.Column("stock_quantity", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
    )
    op.create_index("ix_products_business_hsn", "products", ["business_id", "hsn_code"])

    # Feature 1 & 2: Invoice GST breakdown, cancellation metadata & item HSN/GST split
    op.add_column(
        "invoices",
        sa.Column("gst_mode", sa.String(length=16), nullable=False, server_default="auto"),
    )
    op.add_column(
        "invoices",
        sa.Column("gst_type", sa.String(length=16), nullable=False, server_default="cgst_sgst"),
    )
    op.add_column(
        "invoices",
        sa.Column("cgst_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoices",
        sa.Column("sgst_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoices",
        sa.Column("igst_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column("invoices", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("cancellation_reason", sa.String(length=500), nullable=True))

    op.add_column("invoice_items", sa.Column("hsn_code", sa.String(length=16), nullable=True))
    op.add_column(
        "invoice_items",
        sa.Column("cgst_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoice_items",
        sa.Column("sgst_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoice_items",
        sa.Column("igst_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoice_items",
        sa.Column("cgst_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoice_items",
        sa.Column("sgst_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "invoice_items",
        sa.Column("igst_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
    )

    op.create_table(
        "invoice_modifications",
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
        sa.Column(
            "modified_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("modified_by_name", sa.String(length=160), nullable=False),
        sa.Column("modified_by_email", sa.String(length=254), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("changes_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_invoice_modifications_business_id", "invoice_modifications", ["business_id"])
    op.create_index("ix_invoice_modifications_invoice_id", "invoice_modifications", ["invoice_id"])
    op.create_index(
        "ix_invoice_modifications_invoice_created",
        "invoice_modifications",
        ["invoice_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoice_modifications_invoice_created", table_name="invoice_modifications")
    op.drop_index("ix_invoice_modifications_invoice_id", table_name="invoice_modifications")
    op.drop_index("ix_invoice_modifications_business_id", table_name="invoice_modifications")
    op.drop_table("invoice_modifications")

    op.drop_column("invoice_items", "igst_amount")
    op.drop_column("invoice_items", "sgst_amount")
    op.drop_column("invoice_items", "cgst_amount")
    op.drop_column("invoice_items", "igst_rate")
    op.drop_column("invoice_items", "sgst_rate")
    op.drop_column("invoice_items", "cgst_rate")
    op.drop_column("invoice_items", "hsn_code")

    op.drop_column("invoices", "cancellation_reason")
    op.drop_column("invoices", "cancelled_at")
    op.drop_column("invoices", "igst_amount")
    op.drop_column("invoices", "sgst_amount")
    op.drop_column("invoices", "cgst_amount")
    op.drop_column("invoices", "gst_type")
    op.drop_column("invoices", "gst_mode")

    op.drop_index("ix_products_business_hsn", table_name="products")
    op.drop_column("products", "stock_quantity")
    op.drop_column("products", "purchase_price")
    op.drop_column("products", "hsn_code")

    op.drop_column("businesses", "upi_id")
    op.drop_column("businesses", "bank_branch")
    op.drop_column("businesses", "bank_ifsc_code")
    op.drop_column("businesses", "bank_account_number")
    op.drop_column("businesses", "bank_name")
    op.drop_column("businesses", "bank_account_holder")
