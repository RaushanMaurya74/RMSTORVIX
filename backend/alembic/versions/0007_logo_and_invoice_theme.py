"""Add business logo reference and invoice appearance/theme color columns.

Revision ID: 0007_logo_and_invoice_theme
Revises: 0006_signature_and_gstin
Create Date: 2026-11-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_logo_and_invoice_theme"
down_revision: str | Sequence[str] | None = "0006_signature_and_gstin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("logo_storage_key", sa.String(length=255), nullable=True))
    op.add_column("businesses", sa.Column("logo_mime_type", sa.String(length=40), nullable=True))
    op.add_column(
        "businesses",
        sa.Column("logo_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "businesses",
        sa.Column(
            "invoice_theme_preset",
            sa.String(length=40),
            nullable=False,
            server_default="classic_blue",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_primary_color",
            sa.String(length=7),
            nullable=False,
            server_default="#2563EB",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_secondary_color",
            sa.String(length=7),
            nullable=False,
            server_default="#1E40AF",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_accent_color",
            sa.String(length=7),
            nullable=False,
            server_default="#EFF6FF",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_header_color",
            sa.String(length=7),
            nullable=False,
            server_default="#F8FAFC",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_table_header_color",
            sa.String(length=7),
            nullable=False,
            server_default="#EFF6FF",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_text_color",
            sa.String(length=7),
            nullable=False,
            server_default="#172033",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "theme_border_color",
            sa.String(length=7),
            nullable=False,
            server_default="#E2E8F0",
        ),
    )


def downgrade() -> None:
    op.drop_column("businesses", "theme_border_color")
    op.drop_column("businesses", "theme_text_color")
    op.drop_column("businesses", "theme_table_header_color")
    op.drop_column("businesses", "theme_header_color")
    op.drop_column("businesses", "theme_accent_color")
    op.drop_column("businesses", "theme_secondary_color")
    op.drop_column("businesses", "theme_primary_color")
    op.drop_column("businesses", "invoice_theme_preset")

    op.drop_column("businesses", "logo_updated_at")
    op.drop_column("businesses", "logo_mime_type")
    op.drop_column("businesses", "logo_storage_key")
