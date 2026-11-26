"""Protected Invoice CRUD, editing, cancellation, PDF, and payment QR routes."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_active_subscription_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceStatusType,
    InvoiceUpdate,
    InvoiceVoidRequest,
)
from app.services.invoice_service import (
    create_invoice,
    delete_draft_invoice,
    get_owned_invoice,
    issue_invoice,
    list_invoices,
    serialize_invoice,
    update_invoice,
    void_invoice,
)
from app.services.pdf_service import (
    generate_and_store_invoice_pdf,
    refresh_stored_invoice_pdf,
)
from app.services.qr_service import get_invoice_qr_png
from app.services.saas_service import enforce_plan_feature_limit

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="List invoices for the authenticated business",
)
def read_invoices(
    q: str | None = Query(default=None, max_length=120),
    status_filter: InvoiceStatusType | None = Query(default=None, alias="status"),
    customer_id: int | None = Query(default=None, ge=1),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceListResponse:
    """Search, filter, and paginate invoices owned by the signed-in business."""
    items, total, total_pages = list_invoices(
        db,
        business_id=current_user.business_id,
        q=q,
        status_filter=status_filter,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return InvoiceListResponse(
        items=[serialize_invoice(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invoice with server-calculated GST totals",
)
def create_invoice_route(
    payload: InvoiceCreate,
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Create a draft or issued invoice transactionally."""
    enforce_plan_feature_limit(db, business=current_user.business, resource="invoices")
    invoice = create_invoice(db, current_user=current_user, payload=payload)
    return serialize_invoice(invoice)


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Get an invoice by ID",
)
def read_invoice(
    invoice_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Return an invoice owned by the signed-in business."""
    invoice = get_owned_invoice(
        db, business_id=current_user.business_id, invoice_id=invoice_id
    )
    return serialize_invoice(invoice)


@router.put(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Edit an existing draft or unpaid issued invoice",
)
def update_invoice_route(
    payload: InvoiceUpdate,
    invoice_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Update an editable invoice, record modification history, and refresh PDF if present."""
    invoice, had_pdf = update_invoice(
        db, current_user=current_user, invoice_id=invoice_id, payload=payload
    )
    if had_pdf:
        refresh_stored_invoice_pdf(db, invoice=invoice)
        invoice = get_owned_invoice(
            db, business_id=current_user.business_id, invoice_id=invoice_id
        )
    return serialize_invoice(invoice)


@router.post(
    "/{invoice_id}/issue",
    response_model=InvoiceResponse,
    summary="Issue a draft invoice",
)
def issue_invoice_route(
    invoice_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Mark a draft invoice as issued."""
    invoice = issue_invoice(db, current_user=current_user, invoice_id=invoice_id)
    return serialize_invoice(invoice)


@router.post(
    "/{invoice_id}/void",
    response_model=InvoiceResponse,
    summary="Cancel/void an unpaid invoice",
)
def void_invoice_route(
    invoice_id: int = Path(ge=1),
    payload: InvoiceVoidRequest | None = Body(default=None),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Cancel/void an unpaid invoice while preserving audit and modification history."""
    invoice = void_invoice(
        db,
        current_user=current_user,
        invoice_id=invoice_id,
        reason=payload.reason if payload else None,
    )
    return serialize_invoice(invoice)


@router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an eligible draft or cancelled unpaid invoice",
)
def delete_invoice_route(
    invoice_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> Response:
    """Permanently delete an eligible owned invoice without recorded payments."""
    delete_draft_invoice(db, current_user=current_user, invoice_id=invoice_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{invoice_id}/pdf",
    summary="Download or preview an authorized invoice PDF",
)
def download_invoice_pdf(
    invoice_id: int = Path(ge=1),
    disposition: Literal["attachment", "inline"] = Query(default="attachment"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Generate and stream the PDF for an invoice owned by the signed-in business."""
    enforce_plan_feature_limit(db, business=current_user.business, resource="pdf")
    pdf_bytes, filename = generate_and_store_invoice_pdf(
        db, current_user=current_user, invoice_id=invoice_id
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/{invoice_id}/qr",
    summary="Render an amount-specific UPI payment QR code for an unpaid invoice",
)
def get_invoice_payment_qr(
    invoice_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Generate a PNG QR code for the exact remaining balance due."""
    png_bytes = get_invoice_qr_png(
        db, business_id=current_user.business_id, invoice_id=invoice_id
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )
