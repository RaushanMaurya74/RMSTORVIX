"""Add business visual signature fields and customer gstin_verified flag.

Revision ID: 0006_signature_and_gstin
Revises: 0005_hsn_gst_history_bank
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_signature_and_gstin"
down_revision: str | Sequence[str] | None = "0005_hsn_gst_history_bank"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("signature_storage_key", sa.String(length=255), nullable=True))
    op.add_column("businesses", sa.Column("signature_mime_type", sa.String(length=40), nullable=True))
    op.add_column(
        "businesses",
        sa.Column("signature_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "signature_placement",
            sa.String(length=20),
            nullable=False,
            server_default="bottom_right",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column("signature_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "customers",
        sa.Column("gstin_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("customers", "gstin_verified")

    op.drop_column("businesses", "signature_updated_at")
    op.drop_column("businesses", "signature_placement")
    op.drop_column("businesses", "signature_enabled")
    op.drop_column("businesses", "signature_mime_type")
    op.drop_column("businesses", "signature_storage_key")
