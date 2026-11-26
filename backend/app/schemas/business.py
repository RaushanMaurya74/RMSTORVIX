"""Pydantic schemas for business profile, bank/payment, logo, signature, and invoice themes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.schemas.common import (
    CurrencyCode,
    HexColor,
    OptionalCleanText,
    OptionalEmail,
    OptionalIfscCode,
    OptionalUpiId,
)

SignaturePlacementType = Literal["bottom_left", "bottom_center", "bottom_right"]
InvoiceThemePresetType = Literal[
    "classic_blue",
    "elegant_black",
    "emerald_green",
    "royal_purple",
    "modern_orange",
    "minimal_grey",
    "crimson_red",
    "teal_professional",
    "custom",
]


class InvoiceThemeColors(BaseModel):
    """Validated custom invoice theme palette."""

    preset: InvoiceThemePresetType = Field(default="classic_blue")
    primary_color: HexColor = Field(default="#2563EB")
    secondary_color: HexColor = Field(default="#1E40AF")
    accent_color: HexColor = Field(default="#EFF6FF")
    header_color: HexColor = Field(default="#F8FAFC")
    table_header_color: HexColor = Field(default="#EFF6FF")
    text_color: HexColor = Field(default="#172033")
    border_color: HexColor = Field(default="#E2E8F0")


class InvoiceThemeUpdate(InvoiceThemeColors):
    """Payload to save invoice appearance / theme colors."""


class InvoiceThemePresetResponse(InvoiceThemeColors):
    """Built-in invoice theme preset definition."""

    key: str
    name: str
    description: str


class InvoiceThemeResponse(BaseModel):
    """Current invoice theme settings together with available presets."""

    theme: InvoiceThemeColors
    presets: list[InvoiceThemePresetResponse]


class BusinessAppearanceResponse(BaseModel):
    """Combined business logo status and invoice theme configuration."""

    has_logo: bool
    logo_updated_at: datetime | None = None
    has_signature: bool
    signature_enabled: bool
    signature_placement: str
    signature_updated_at: datetime | None = None
    theme: InvoiceThemeColors
    presets: list[InvoiceThemePresetResponse]


class BusinessProfileResponse(BaseModel):
    """Serialized business profile scoped to the authenticated account."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    legal_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    tax_id: str | None = None
    business_type: str | None = None
    mobile: str | None = None
    subscription_status: str = "NOT_ACTIVATED"
    currency_code: str
    invoice_prefix: str
    next_invoice_number: int
    bank_account_holder: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    bank_branch: str | None = None
    upi_id: str | None = None
    signature_storage_key: str | None = Field(default=None, exclude=True)
    signature_enabled: bool = False
    signature_placement: str = "bottom_right"
    signature_updated_at: datetime | None = None
    logo_storage_key: str | None = Field(default=None, exclude=True)
    logo_updated_at: datetime | None = None
    invoice_theme_preset: str = "classic_blue"
    theme_primary_color: str = "#2563EB"
    theme_secondary_color: str = "#1E40AF"
    theme_accent_color: str = "#EFF6FF"
    theme_header_color: str = "#F8FAFC"
    theme_table_header_color: str = "#EFF6FF"
    theme_text_color: str = "#172033"
    theme_border_color: str = "#E2E8F0"
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_signature(self) -> bool:
        """Whether a visual signature image is configured (without exposing storage paths)."""
        return bool(self.signature_storage_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_logo(self) -> bool:
        """Whether a business logo image is configured (without exposing storage paths)."""
        return bool(self.logo_storage_key)


class BusinessProfileUpdate(BaseModel):
    """Validated update payload for business profile, invoice defaults, and bank details."""

    name: str = Field(min_length=2, max_length=160)
    legal_name: OptionalCleanText = Field(default=None, max_length=200)
    email: OptionalEmail = None
    phone: OptionalCleanText = Field(default=None, max_length=40)
    address_line1: OptionalCleanText = Field(default=None, max_length=200)
    address_line2: OptionalCleanText = Field(default=None, max_length=200)
    city: OptionalCleanText = Field(default=None, max_length=100)
    state: OptionalCleanText = Field(default=None, max_length=100)
    postal_code: OptionalCleanText = Field(default=None, max_length=30)
    country: OptionalCleanText = Field(default=None, max_length=100)
    tax_id: OptionalCleanText = Field(default=None, max_length=64)
    business_type: OptionalCleanText = Field(default=None, max_length=80)
    mobile: OptionalCleanText = Field(default=None, max_length=40)
    currency_code: CurrencyCode = Field(default="USD")
    invoice_prefix: str = Field(default="INV-", min_length=1, max_length=20)
    next_invoice_number: int = Field(default=1, ge=1, le=999_999_999)
    bank_account_holder: OptionalCleanText = Field(default=None, max_length=160)
    bank_name: OptionalCleanText = Field(default=None, max_length=160)
    bank_account_number: OptionalCleanText = Field(default=None, max_length=64)
    bank_ifsc_code: OptionalIfscCode = None
    bank_branch: OptionalCleanText = Field(default=None, max_length=160)
    upi_id: OptionalUpiId = None
    signature_enabled: bool | None = None
    signature_placement: SignaturePlacementType | None = None

    @field_validator("name", "invoice_prefix")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank.")
        return cleaned
