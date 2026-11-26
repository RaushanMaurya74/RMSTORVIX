"""Business profile SQLAlchemy model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


class Business(Base):
    """Represents a business account that owns customers, products, and invoices."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subscription_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="NOT_ACTIVATED",
        server_default="NOT_ACTIVATED",
        index=True,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    invoice_prefix: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INV-", server_default="INV-"
    )
    next_invoice_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # Bank & UPI payment configuration
    bank_account_holder: Mapped[str | None] = mapped_column(String(160), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bank_ifsc_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(String(160), nullable=True)
    upi_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Visual signature configuration (stored in managed signature dir; never exposed publicly)
    signature_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signature_mime_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    signature_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    signature_placement: Mapped[str] = mapped_column(
        String(20), nullable=False, default="bottom_right", server_default="bottom_right"
    )
    signature_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Business logo configuration (stored in managed logo dir; never exposed publicly)
    logo_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_mime_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    logo_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Custom invoice theme & colors
    invoice_theme_preset: Mapped[str] = mapped_column(
        String(40), nullable=False, default="classic_blue", server_default="classic_blue"
    )
    theme_primary_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#2563EB", server_default="#2563EB"
    )
    theme_secondary_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#1E40AF", server_default="#1E40AF"
    )
    theme_accent_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#EFF6FF", server_default="#EFF6FF"
    )
    theme_header_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#F8FAFC", server_default="#F8FAFC"
    )
    theme_table_header_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#EFF6FF", server_default="#EFF6FF"
    )
    theme_text_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#172033", server_default="#172033"
    )
    theme_border_color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#E2E8F0", server_default="#E2E8F0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="business")
