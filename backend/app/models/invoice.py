"""Invoice, InvoiceItem, and InvoiceModification SQLAlchemy models."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.customer import Customer


class Invoice(Base):
    """Invoice header owned by a Business and billed to a Customer."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("business_id", "invoice_number", name="uq_invoices_business_number"),
        Index("ix_invoices_business_status", "business_id", "status"),
        Index("ix_invoices_business_issue_date", "business_id", "issue_date"),
        Index("ix_invoices_business_customer", "business_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )
    gst_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="auto", server_default="auto"
    )
    gst_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cgst_sgst", server_default="cgst_sgst"
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)

    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    balance_due: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Managed relative storage filename (never exposed in API responses)
    pdf_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pdf_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    business: Mapped["Business"] = relationship("Business")
    customer: Mapped["Customer"] = relationship("Customer")
    items: Mapped[list["InvoiceItem"]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.position",
    )
    modifications: Mapped[list["InvoiceModification"]] = relationship(
        "InvoiceModification",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceModification.created_at.desc(), InvoiceModification.id.desc()",
    )


class InvoiceItem(Base):
    """Server-calculated invoice line item snapshot."""

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    hsn_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    tax_label: Mapped[str | None] = mapped_column(String(40), nullable=True)

    cgst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    sgst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    igst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")


class InvoiceModification(Base):
    """Immutable modification history entry tracking who changed an invoice, when, and what."""

    __tablename__ = "invoice_modifications"
    __table_args__ = (
        Index("ix_invoice_modifications_invoice_created", "invoice_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modified_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    modified_by_name: Mapped[str] = mapped_column(String(160), nullable=False)
    modified_by_email: Mapped[str] = mapped_column(String(254), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    changes_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="modifications")
