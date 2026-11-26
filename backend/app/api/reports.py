"""Protected Reports, CSV export, and Audit Trail routes."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.report import (
    AuditEventListResponse,
    AuditEventResponse,
    SalesReportResponse,
)
from app.services.report_service import (
    export_invoices_csv,
    get_sales_summary,
    list_audit_events,
)
from app.services.saas_service import enforce_plan_feature_limit

router = APIRouter(prefix="/reports", tags=["Reports & Audit"])


@router.get(
    "/summary",
    response_model=SalesReportResponse,
    summary="Get sales, tax, collections, and invoice status summary",
)
def read_sales_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesReportResponse:
    """Aggregate sales and invoice metrics scoped to the signed-in business."""
    enforce_plan_feature_limit(db, business=current_user.business, resource="reports")
    return get_sales_summary(
        db,
        business_id=current_user.business_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/invoices.csv",
    summary="Export invoices as CSV",
)
def download_invoices_csv(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Export business-scoped invoices as a downloadable CSV file."""
    csv_content = export_invoices_csv(
        db,
        business_id=current_user.business_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="invoices_export.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/audit",
    response_model=AuditEventListResponse,
    summary="List recent audit events for the authenticated business",
)
def read_audit_events(
    action: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditEventListResponse:
    """Return paginated audit events scoped to the signed-in business."""
    items, total, total_pages = list_audit_events(
        db,
        business_id=current_user.business_id,
        action=action,
        page=page,
        page_size=page_size,
    )
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
