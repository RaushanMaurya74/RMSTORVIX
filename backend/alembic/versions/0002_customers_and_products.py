"""Add customers and products tables.

Revision ID: 0002_customers_and_products
Revises: 0001_initial_auth_and_business
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_customers_and_products"
down_revision: str | Sequence[str] | None = "0001_initial_auth_and_business"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("company_name", sa.String(length=180), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
        sa.Column("address_line1", sa.String(length=200), nullable=True),
        sa.Column("address_line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=30), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    )
    op.create_index("ix_customers_business_id", "customers", ["business_id"])
    op.create_index("ix_customers_business_name", "customers", ["business_id", "name"])
    op.create_index("ix_customers_business_active", "customers", ["business_id", "is_active"])

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "tax_rate",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("tax_label", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    )
    op.create_index("ix_products_business_id", "products", ["business_id"])
    op.create_index("ix_products_business_name", "products", ["business_id", "name"])
    op.create_index("ix_products_business_active", "products", ["business_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_products_business_active", table_name="products")
    op.drop_index("ix_products_business_name", table_name="products")
    op.drop_index("ix_products_business_id", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_customers_business_active", table_name="customers")
    op.drop_index("ix_customers_business_name", table_name="customers")
    op.drop_index("ix_customers_business_id", table_name="customers")
    op.drop_table("customers")
