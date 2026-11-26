"""Protected Business Profile, Logo, Visual Signature, and Invoice Theme endpoints."""

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_active_subscription_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.business import (
    BusinessAppearanceResponse,
    BusinessProfileResponse,
    BusinessProfileUpdate,
    InvoiceThemeColors,
    InvoiceThemeResponse,
    InvoiceThemeUpdate,
)
from app.services.business_service import get_business_profile, update_business_profile
from app.services.logo_service import (
    get_business_logo_bytes,
    remove_business_logo,
    upload_business_logo,
)
from app.services.saas_service import enforce_plan_feature_limit
from app.services.signature_service import (
    get_business_signature_bytes,
    remove_business_signature,
    upload_business_signature,
)
from app.services.storage_service import create_signed_storage_url
from app.services.theme_service import (
    get_theme_presets_payload,
    resolve_business_theme,
    update_business_theme,
)

router = APIRouter(prefix="/business", tags=["Business Profile"])


@router.get(
    "",
    response_model=BusinessProfileResponse,
    summary="Get the authenticated user's business profile",
)
def read_business_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BusinessProfileResponse:
    """Return the business profile scoped to the signed-in user."""
    business = get_business_profile(db, business_id=current_user.business_id)
    return BusinessProfileResponse.model_validate(business)


@router.put(
    "",
    response_model=BusinessProfileResponse,
    summary="Update the authenticated user's business profile",
)
def save_business_profile(
    payload: BusinessProfileUpdate,
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> BusinessProfileResponse:
    """Update business profile details, bank settings, and signature preferences."""
    business = update_business_profile(db, current_user=current_user, payload=payload)
    return BusinessProfileResponse.model_validate(business)


@router.get(
    "/appearance",
    response_model=BusinessAppearanceResponse,
    summary="Retrieve business logo status, signature status, and invoice theme settings",
)
def read_business_appearance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BusinessAppearanceResponse:
    """Return business appearance metadata and theme presets without exposing paths."""
    business = get_business_profile(db, business_id=current_user.business_id)
    return BusinessAppearanceResponse(
        has_logo=bool(business.logo_storage_key),
        logo_updated_at=business.logo_updated_at,
        has_signature=bool(business.signature_storage_key),
        signature_enabled=bool(business.signature_enabled),
        signature_placement=business.signature_placement or "bottom_right",
        signature_updated_at=business.signature_updated_at,
        theme=InvoiceThemeColors(**resolve_business_theme(business)),
        presets=get_theme_presets_payload(),
    )


@router.get(
    "/theme",
    response_model=InvoiceThemeResponse,
    summary="Retrieve saved invoice theme settings and available presets",
)
def read_invoice_theme(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceThemeResponse:
    """Return the authenticated business's invoice theme palette and presets."""
    business = get_business_profile(db, business_id=current_user.business_id)
    return InvoiceThemeResponse(
        theme=InvoiceThemeColors(**resolve_business_theme(business)),
        presets=get_theme_presets_payload(),
    )


@router.put(
    "/theme",
    response_model=InvoiceThemeResponse,
    summary="Save custom invoice theme preset and colors",
)
def save_invoice_theme(
    payload: InvoiceThemeUpdate,
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> InvoiceThemeResponse:
    """Validate and persist invoice appearance colors and invalidate cached PDFs."""
    enforce_plan_feature_limit(db, business=current_user.business, resource="themes")
    business = update_business_theme(db, current_user=current_user, payload=payload)
    return InvoiceThemeResponse(
        theme=InvoiceThemeColors(**resolve_business_theme(business)),
        presets=get_theme_presets_payload(),
    )


@router.get(
    "/logo",
    summary="Fetch the authenticated business's logo image",
)
def read_business_logo(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve the configured business logo only to authenticated business members."""
    image_bytes, mime_type = get_business_logo_bytes(db, business_id=current_user.business_id)
    return Response(
        content=image_bytes,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get(
    "/logo/signed-url",
    summary="Issue a short-lived signed URL for the business logo when using Supabase Storage",
)
def read_business_logo_signed_url(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Return a short-lived signed URL (or direct authenticated API URL on local storage)."""
    business = get_business_profile(db, business_id=current_user.business_id)
    signed = create_signed_storage_url(namespace="logos", storage_key=business.logo_storage_key)
    return {"url": signed or "/api/v1/business/logo"}


@router.post(
    "/logo",
    response_model=BusinessProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload the business logo image",
)
@router.put(
    "/logo",
    response_model=BusinessProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Replace the business logo image",
)
async def upload_logo_route(
    file: UploadFile = File(...),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> BusinessProfileResponse:
    """Validate and store/replace a PNG, JPG/JPEG, or WebP business logo image."""
    raw_bytes = await file.read()
    business = upload_business_logo(
        db,
        current_user=current_user,
        file_bytes=raw_bytes,
        content_type=file.content_type,
    )
    return BusinessProfileResponse.model_validate(business)


@router.delete(
    "/logo",
    response_model=BusinessProfileResponse,
    summary="Remove the business logo image",
)
def delete_logo_route(
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> BusinessProfileResponse:
    """Delete the stored business logo image and clear DB reference."""
    business = remove_business_logo(db, current_user=current_user)
    return BusinessProfileResponse.model_validate(business)


@router.get(
    "/signature",
    summary="Fetch the authenticated business's visual signature image",
)
def read_business_signature(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve the configured signature image only to authenticated members of the business."""
    image_bytes, mime_type = get_business_signature_bytes(
        db, business_id=current_user.business_id
    )
    return Response(
        content=image_bytes,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get(
    "/signature/signed-url",
    summary="Issue a short-lived signed URL for the business signature when using Supabase Storage",
)
def read_business_signature_signed_url(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Return a short-lived signed URL (or direct authenticated API URL on local storage)."""
    business = get_business_profile(db, business_id=current_user.business_id)
    signed = create_signed_storage_url(
        namespace="signatures", storage_key=business.signature_storage_key
    )
    return {"url": signed or "/api/v1/business/signature"}


@router.post(
    "/signature",
    response_model=BusinessProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload or replace the business visual signature image",
)
async def upload_signature_route(
    file: UploadFile = File(...),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> BusinessProfileResponse:
    """Validate and store a PNG, JPG/JPEG, or WebP visual signature image."""
    raw_bytes = await file.read()
    business = upload_business_signature(
        db,
        current_user=current_user,
        file_bytes=raw_bytes,
        content_type=file.content_type,
    )
    return BusinessProfileResponse.model_validate(business)


@router.delete(
    "/signature",
    response_model=BusinessProfileResponse,
    summary="Remove the business visual signature image",
)
def delete_signature_route(
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> BusinessProfileResponse:
    """Delete the stored signature image and disable signatures on invoices."""
    business = remove_business_signature(db, current_user=current_user)
    return BusinessProfileResponse.model_validate(business)
