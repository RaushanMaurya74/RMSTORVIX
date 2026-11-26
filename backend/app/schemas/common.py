"""Shared Pydantic validation helpers."""

import re
from typing import Annotated

from pydantic import AfterValidator

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_HSN_PATTERN = re.compile(r"^\d{4}(\d{2}(\d{2})?)?$")
_IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_UPI_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+$")
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")


def validate_email_value(value: str) -> str:
    """Normalize and validate an email address."""
    cleaned = value.strip().lower()
    if len(cleaned) > 254 or not _EMAIL_PATTERN.match(cleaned):
        raise ValueError("Enter a valid email address.")
    return cleaned


def validate_optional_email_value(value: str | None) -> str | None:
    """Normalize and validate an optional email address."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return validate_email_value(cleaned)


def clean_optional_text(value: str | None) -> str | None:
    """Trim optional strings and convert blank strings to None."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def validate_currency_code(value: str) -> str:
    """Validate and uppercase a 3-letter ISO currency code."""
    cleaned = value.strip().upper()
    if not _CURRENCY_PATTERN.match(cleaned):
        raise ValueError("Currency code must be a 3-letter ISO code (e.g. USD, INR, EUR).")
    return cleaned


def validate_optional_hsn_code(value: str | None) -> str | None:
    """Validate optional 4, 6, or 8 digit HSN code."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _HSN_PATTERN.match(cleaned):
        raise ValueError("HSN code must be 4, 6, or 8 digits (e.g. 9983 or 847130).")
    return cleaned


def validate_optional_ifsc(value: str | None) -> str | None:
    """Validate optional 11-character IFSC code."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if not _IFSC_PATTERN.match(cleaned):
        raise ValueError("IFSC code must be 11 characters (e.g. SBIN0001234).")
    return cleaned


def validate_optional_upi_id(value: str | None) -> str | None:
    """Validate optional UPI VPA address."""
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if len(cleaned) > 120 or not _UPI_PATTERN.match(cleaned):
        raise ValueError("Enter a valid UPI ID (e.g. business@upi).")
    return cleaned


def validate_hex_color(value: str) -> str:
    """Validate and normalize a 6-digit hex color string (#RRGGBB)."""
    cleaned = value.strip().upper()
    if not _HEX_COLOR_PATTERN.match(cleaned):
        raise ValueError("Color must be a valid 6-digit hex code (e.g. #2563EB).")
    return cleaned


NormalizedEmail = Annotated[str, AfterValidator(validate_email_value)]
OptionalEmail = Annotated[str | None, AfterValidator(validate_optional_email_value)]
OptionalCleanText = Annotated[str | None, AfterValidator(clean_optional_text)]
CurrencyCode = Annotated[str, AfterValidator(validate_currency_code)]
OptionalHsnCode = Annotated[str | None, AfterValidator(validate_optional_hsn_code)]
OptionalIfscCode = Annotated[str | None, AfterValidator(validate_optional_ifsc)]
OptionalUpiId = Annotated[str | None, AfterValidator(validate_optional_upi_id)]
HexColor = Annotated[str, AfterValidator(validate_hex_color)]
