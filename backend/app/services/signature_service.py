"""Authorized visual signature image upload, validation, storage, and retrieval."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.business import Business
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.media_service import (
    delete_stored_asset,
    invalidate_business_pdfs,
    load_image_png_for_pdf,
    read_stored_asset_bytes,
    validate_and_store_image,
)


def upload_business_signature(
    db: Session,
    *,
    current_user: User,
    file_bytes: bytes,
    content_type: str | None,
    settings: Settings | None = None,
) -> Business:
    """Validate and store a business visual signature image (PNG, JPEG, or WebP)."""
    active_settings = settings or get_settings()
    business = db.get(Business, current_user.business_id)
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found.",
        )

    new_key, canonical_mime, width, height = validate_and_store_image(
        base_dir=active_settings.resolved_signature_dir,
        business_id=business.id,
        asset_name="signature",
        asset_label="signature",
        file_bytes=file_bytes,
        content_type=content_type,
        max_bytes=active_settings.signature_max_bytes,
        previous_key=business.signature_storage_key,
        namespace="signatures",
        settings=active_settings,
    )

    business.signature_storage_key = new_key
    business.signature_mime_type = canonical_mime
    business.signature_enabled = True
    business.signature_updated_at = datetime.now(timezone.utc)
    invalidate_business_pdfs(db, business_id=business.id)

    record_audit_event(
        db,
        business_id=business.id,
        user_id=current_user.id,
        action="business.signature_uploaded",
        entity_type="business",
        entity_id=business.id,
        details={"mime_type": canonical_mime, "width": width, "height": height},
    )
    db.commit()
    db.refresh(business)
    return business


def get_business_signature_bytes(
    db: Session,
    *,
    business_id: int,
    settings: Settings | None = None,
) -> tuple[bytes, str]:
    """Retrieve the authenticated business's signature bytes and MIME type."""
    active_settings = settings or get_settings()
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature image not configured.",
        )
    return read_stored_asset_bytes(
        base_dir=active_settings.resolved_signature_dir,
        storage_key=business.signature_storage_key,
        mime_type=business.signature_mime_type,
        asset_label="signature",
        namespace="signatures",
        settings=active_settings,
    )


def remove_business_signature(
    db: Session,
    *,
    current_user: User,
    settings: Settings | None = None,
) -> Business:
    """Remove the visual signature image and disable it on future invoices."""
    active_settings = settings or get_settings()
    business = db.get(Business, current_user.business_id)
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found.",
        )

    delete_stored_asset(
        active_settings.resolved_signature_dir,
        business.signature_storage_key,
        asset_label="signature",
        namespace="signatures",
        settings=active_settings,
    )

    business.signature_storage_key = None
    business.signature_mime_type = None
    business.signature_enabled = False
    business.signature_updated_at = None
    invalidate_business_pdfs(db, business_id=business.id)

    record_audit_event(
        db,
        business_id=business.id,
        user_id=current_user.id,
        action="business.signature_removed",
        entity_type="business",
        entity_id=business.id,
    )
    db.commit()
    db.refresh(business)
    return business


def load_signature_png_for_pdf(
    business: Business | None,
    *,
    settings: Settings | None = None,
) -> tuple[bytes, int, int] | None:
    """Load and convert an enabled signature image to PNG bytes with dimensions for PDFs."""
    if business is None or not business.signature_enabled or not business.signature_storage_key:
        return None
    active_settings = settings or get_settings()
    return load_image_png_for_pdf(
        base_dir=active_settings.resolved_signature_dir,
        storage_key=business.signature_storage_key,
        asset_label="signature",
        namespace="signatures",
        settings=active_settings,
    )
