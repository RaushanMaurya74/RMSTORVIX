"""Shared authenticated image validation, storage containment, and PDF conversion helpers."""

import io
from pathlib import Path

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.invoice import Invoice
from app.services.storage_service import (
    delete_stored_object,
    get_stored_bytes,
    put_stored_bytes,
    safe_local_path,
)

_ALLOWED_FORMATS: dict[str, tuple[str, str]] = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
}

_ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}

_MAX_IMAGE_PIXELS = 25_000_000


def safe_asset_path(base_dir: Path, storage_key: str, *, asset_label: str = "asset") -> Path:
    """Resolve storage_key strictly inside base_dir and block path traversal."""
    return safe_local_path(base_dir, storage_key, asset_label=asset_label)


def invalidate_business_pdfs(db: Session, *, business_id: int) -> None:
    """Clear cached invoice PDF paths so regenerated PDFs reflect updated assets/themes."""
    db.execute(
        update(Invoice)
        .where(Invoice.business_id == business_id)
        .values(pdf_storage_key=None, pdf_generated_at=None)
    )


def delete_stored_asset(
    base_dir: Path,
    storage_key: str | None,
    *,
    asset_label: str,
    namespace: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Remove an existing managed file cleanly across local or Supabase Storage."""
    delete_stored_object(
        namespace=namespace or f"{asset_label}s",
        base_dir=base_dir,
        storage_key=storage_key,
        asset_label=asset_label,
        settings=settings,
    )


def validate_and_store_image(
    *,
    base_dir: Path,
    business_id: int,
    asset_name: str,
    asset_label: str,
    file_bytes: bytes,
    content_type: str | None,
    max_bytes: int,
    previous_key: str | None,
    namespace: str | None = None,
    settings: Settings | None = None,
) -> tuple[str, str, int, int]:
    """Validate an uploaded PNG/JPEG/WebP image and write it safely to persistent storage."""
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{asset_label.capitalize()} image file is empty.",
        )
    if len(file_bytes) > max_bytes:
        max_mb = round(max_bytes / (1024 * 1024), 1)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{asset_label.capitalize()} image exceeds maximum allowed size ({max_mb} MB).",
        )

    if content_type and content_type.split(";")[0].strip().lower() not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported {asset_label} file type. Upload PNG, JPG/JPEG, or WebP.",
        )

    try:
        with Image.open(io.BytesIO(file_bytes)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(file_bytes)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file is not a valid image.",
        ) from exc

    if fmt not in _ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported image format. Upload PNG, JPG/JPEG, or WebP.",
        )
    if width < 1 or height < 1 or (width * height) > _MAX_IMAGE_PIXELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{asset_label.capitalize()} image dimensions are invalid or too large.",
        )

    ext, canonical_mime = _ALLOWED_FORMATS[fmt]
    new_key = f"biz_{business_id}/{asset_name}.{ext}"
    ns = namespace or f"{asset_label}s"
    active_settings = settings or get_settings()

    put_stored_bytes(
        namespace=ns,
        base_dir=base_dir,
        storage_key=new_key,
        data=file_bytes,
        content_type=canonical_mime,
        asset_label=asset_label,
        settings=active_settings,
    )

    if previous_key and previous_key != new_key:
        delete_stored_asset(
            base_dir,
            previous_key,
            asset_label=asset_label,
            namespace=ns,
            settings=active_settings,
        )

    return new_key, canonical_mime, width, height


def read_stored_asset_bytes(
    *,
    base_dir: Path,
    storage_key: str | None,
    mime_type: str | None,
    asset_label: str,
    namespace: str | None = None,
    settings: Settings | None = None,
) -> tuple[bytes, str]:
    """Read an authenticated business asset file from managed storage."""
    if not storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{asset_label.capitalize()} image not configured.",
        )
    raw = get_stored_bytes(
        namespace=namespace or f"{asset_label}s",
        base_dir=base_dir,
        storage_key=storage_key,
        asset_label=asset_label,
        settings=settings,
    )
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{asset_label.capitalize()} image file not found.",
        )
    return raw, mime_type or "image/png"


def load_image_png_for_pdf(
    *,
    base_dir: Path,
    storage_key: str | None,
    asset_label: str,
    namespace: str | None = None,
    settings: Settings | None = None,
) -> tuple[bytes, int, int] | None:
    """Load an image asset safely and normalize it to PNG bytes + pixel dimensions for fpdf2."""
    if not storage_key:
        return None
    try:
        raw = get_stored_bytes(
            namespace=namespace or f"{asset_label}s",
            base_dir=base_dir,
            storage_key=storage_key,
            asset_label=asset_label,
            settings=settings,
        )
        if not raw:
            return None
        with Image.open(io.BytesIO(raw)) as img:
            width, height = img.size
            if width < 1 or height < 1:
                return None
            converted = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA")
            buf = io.BytesIO()
            converted.save(buf, format="PNG")
            return buf.getvalue(), width, height
    except Exception:
        return None
