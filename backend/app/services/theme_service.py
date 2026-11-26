"""Invoice theme presets, color contrast helpers, and theme update service."""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.user import User
from app.schemas.business import InvoiceThemePresetResponse, InvoiceThemeUpdate
from app.services.audit_service import record_audit_event
from app.services.media_service import invalidate_business_pdfs

DEFAULT_THEME_PRESET = "classic_blue"


@dataclass(frozen=True)
class ThemePresetSpec:
    """Immutable definition for a built-in invoice theme preset."""

    key: str
    name: str
    description: str
    primary_color: str
    secondary_color: str
    accent_color: str
    header_color: str
    table_header_color: str
    text_color: str
    border_color: str


INVOICE_THEME_PRESETS: tuple[ThemePresetSpec, ...] = (
    ThemePresetSpec(
        key="classic_blue",
        name="Classic Blue",
        description="Crisp corporate blue accents on clean white surfaces.",
        primary_color="#2563EB",
        secondary_color="#1E40AF",
        accent_color="#EFF6FF",
        header_color="#F8FAFC",
        table_header_color="#EFF6FF",
        text_color="#172033",
        border_color="#E2E8F0",
    ),
    ThemePresetSpec(
        key="elegant_black",
        name="Elegant Black",
        description="High-contrast charcoal monochrome for executive invoices.",
        primary_color="#111827",
        secondary_color="#374151",
        accent_color="#F3F4F6",
        header_color="#F9FAFB",
        table_header_color="#111827",
        text_color="#111827",
        border_color="#D1D5DB",
    ),
    ThemePresetSpec(
        key="emerald_green",
        name="Emerald Green",
        description="Fresh emerald highlights suited for modern service firms.",
        primary_color="#059669",
        secondary_color="#065F46",
        accent_color="#ECFDF5",
        header_color="#F0FDF4",
        table_header_color="#D1FAE5",
        text_color="#14281D",
        border_color="#A7F3D0",
    ),
    ThemePresetSpec(
        key="royal_purple",
        name="Royal Purple",
        description="Refined indigo-violet accents for creative & tech brands.",
        primary_color="#7C3AED",
        secondary_color="#5B21B6",
        accent_color="#F5F3FF",
        header_color="#FAF5FF",
        table_header_color="#EDE9FE",
        text_color="#1E1B4B",
        border_color="#DDD6FE",
    ),
    ThemePresetSpec(
        key="modern_orange",
        name="Modern Orange",
        description="Warm amber-orange palette with sharp readable slate type.",
        primary_color="#EA580C",
        secondary_color="#9A3412",
        accent_color="#FFF7ED",
        header_color="#FFFBEB",
        table_header_color="#FFEDD5",
        text_color="#1C1917",
        border_color="#FED7AA",
    ),
    ThemePresetSpec(
        key="minimal_grey",
        name="Minimal Grey",
        description="Neutral slate tones with distraction-free print clarity.",
        primary_color="#475569",
        secondary_color="#334155",
        accent_color="#F8FAFC",
        header_color="#F1F5F9",
        table_header_color="#E2E8F0",
        text_color="#0F172A",
        border_color="#CBD5E1",
    ),
    ThemePresetSpec(
        key="crimson_red",
        name="Crimson Red",
        description="Bold crimson header highlights with balanced rose tints.",
        primary_color="#DC2626",
        secondary_color="#991B1B",
        accent_color="#FEF2F2",
        header_color="#FFF5F5",
        table_header_color="#FEE2E2",
        text_color="#1F2937",
        border_color="#FECACA",
    ),
    ThemePresetSpec(
        key="teal_professional",
        name="Teal Professional",
        description="Structured ocean teal header with calm neutral framing.",
        primary_color="#0D9488",
        secondary_color="#115E59",
        accent_color="#F0FDFA",
        header_color="#F0FDFA",
        table_header_color="#0F766E",
        text_color="#134E4A",
        border_color="#99F6E4",
    ),
)

PRESET_BY_KEY: dict[str, ThemePresetSpec] = {preset.key: preset for preset in INVOICE_THEME_PRESETS}
DEFAULT_THEME_SPEC = PRESET_BY_KEY[DEFAULT_THEME_PRESET]


def get_theme_presets_payload() -> list[InvoiceThemePresetResponse]:
    """Return all built-in invoice theme presets for API consumers."""
    return [
        InvoiceThemePresetResponse(
            key=preset.key,
            name=preset.name,
            description=preset.description,
            primary_color=preset.primary_color,
            secondary_color=preset.secondary_color,
            accent_color=preset.accent_color,
            header_color=preset.header_color,
            table_header_color=preset.table_header_color,
            text_color=preset.text_color,
            border_color=preset.border_color,
        )
        for preset in INVOICE_THEME_PRESETS
    ]


def hex_to_rgb(hex_color: str, fallback: str = "#2563EB") -> tuple[int, int, int]:
    """Convert a #RRGGBB string into an (R, G, B) integer tuple."""
    candidate = (hex_color or fallback).strip().lstrip("#")
    if len(candidate) != 6:
        candidate = fallback.lstrip("#")
    try:
        return (
            int(candidate[0:2], 16),
            int(candidate[2:4], 16),
            int(candidate[4:6], 16),
        )
    except ValueError:
        fb = fallback.lstrip("#")
        return int(fb[0:2], 16), int(fb[2:4], 16), int(fb[4:6], 16)


def muted_rgb(rgb: tuple[int, int, int], factor: float = 0.38) -> tuple[int, int, int]:
    """Blend an RGB text color toward white to produce readable secondary/muted copy."""
    return tuple(int(round(c + (255 - c) * factor)) for c in rgb)  # type: ignore[return-value]


def contrast_text_rgb(bg_hex: str, dark_hex: str = "#172033") -> tuple[int, int, int]:
    """Pick white or dark foreground text based on background relative luminance."""
    r, g, b = hex_to_rgb(bg_hex)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    if luminance < 0.54:
        return (255, 255, 255)
    return hex_to_rgb(dark_hex)


def resolve_business_theme(business: Business | None) -> dict[str, str]:
    """Return normalized theme colors for a business with Classic Blue fallbacks."""
    d = DEFAULT_THEME_SPEC
    if business is None:
        return {
            "preset": d.key,
            "primary_color": d.primary_color,
            "secondary_color": d.secondary_color,
            "accent_color": d.accent_color,
            "header_color": d.header_color,
            "table_header_color": d.table_header_color,
            "text_color": d.text_color,
            "border_color": d.border_color,
        }
    return {
        "preset": (business.invoice_theme_preset or d.key),
        "primary_color": (business.theme_primary_color or d.primary_color).upper(),
        "secondary_color": (business.theme_secondary_color or d.secondary_color).upper(),
        "accent_color": (business.theme_accent_color or d.accent_color).upper(),
        "header_color": (business.theme_header_color or d.header_color).upper(),
        "table_header_color": (business.theme_table_header_color or d.table_header_color).upper(),
        "text_color": (business.theme_text_color or d.text_color).upper(),
        "border_color": (business.theme_border_color or d.border_color).upper(),
    }


def update_business_theme(
    db: Session,
    *,
    current_user: User,
    payload: InvoiceThemeUpdate,
) -> Business:
    """Validate and save invoice theme colors & preset for the authenticated business."""
    business = db.get(Business, current_user.business_id)
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found.",
        )

    business.invoice_theme_preset = payload.preset
    business.theme_primary_color = payload.primary_color
    business.theme_secondary_color = payload.secondary_color
    business.theme_accent_color = payload.accent_color
    business.theme_header_color = payload.header_color
    business.theme_table_header_color = payload.table_header_color
    business.theme_text_color = payload.text_color
    business.theme_border_color = payload.border_color

    invalidate_business_pdfs(db, business_id=business.id)
    record_audit_event(
        db,
        business_id=business.id,
        user_id=current_user.id,
        action="business.theme_updated",
        entity_type="business",
        entity_id=business.id,
        details={
            "preset": payload.preset,
            "primary_color": payload.primary_color,
            "table_header_color": payload.table_header_color,
        },
    )
    db.commit()
    db.refresh(business)
    return business
