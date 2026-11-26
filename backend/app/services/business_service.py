"""Business profile service scoped strictly to the authenticated business."""

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.business import BusinessProfileUpdate
from app.services.audit_service import record_audit_event


def get_business_profile(db: Session, *, business_id: int) -> Business:
    """Fetch the business record owned by the authenticated user's business."""
    business = db.scalar(select(Business).where(Business.id == business_id))
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found.",
        )
    return business


def update_business_profile(
    db: Session,
    *,
    current_user: User,
    payload: BusinessProfileUpdate,
) -> Business:
    """Update business details and record an audit event transactionally."""
    business = get_business_profile(db, business_id=current_user.business_id)

    update_data = payload.model_dump()
    if update_data.get("signature_enabled") is None:
        update_data.pop("signature_enabled", None)
    if update_data.get("signature_placement") is None:
        update_data.pop("signature_placement", None)

    changed_fields = [
        field for field, new_value in update_data.items() if getattr(business, field) != new_value
    ]

    for field, value in update_data.items():
        setattr(business, field, value)

    if any(
        f in changed_fields
        for f in (
            "name",
            "legal_name",
            "address_line1",
            "city",
            "state",
            "tax_id",
            "bank_account_holder",
            "bank_name",
            "bank_account_number",
            "bank_ifsc_code",
            "bank_branch",
            "upi_id",
            "signature_enabled",
            "signature_placement",
        )
    ):
        db.execute(
            update(Invoice)
            .where(Invoice.business_id == business.id)
            .values(pdf_storage_key=None, pdf_generated_at=None)
        )

    record_audit_event(
        db,
        business_id=business.id,
        user_id=current_user.id,
        action="business.updated",
        entity_type="business",
        entity_id=business.id,
        details={"changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(business)
    return business
