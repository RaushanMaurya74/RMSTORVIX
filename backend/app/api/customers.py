"""Protected Customer CRUD endpoints."""

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_active_subscription_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
    GstinVerifyRequest,
    GstinVerifyResponse,
)
from app.services.customer_service import (
    create_customer,
    delete_customer,
    get_owned_customer,
    list_customers,
    update_customer,
)
from app.services.gstin_service import verify_and_lookup_gstin
from app.services.saas_service import enforce_plan_feature_limit

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get(
    "",
    response_model=CustomerListResponse,
    summary="List customers for the authenticated business",
)
def read_customers(
    q: str | None = Query(default=None, max_length=120),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    """Search, filter, and paginate customers owned by the signed-in business."""
    items, total, total_pages = list_customers(
        db,
        business_id=current_user.business_id,
        q=q,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return CustomerListResponse(
        items=[CustomerResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
)
def create_customer_route(
    payload: CustomerCreate,
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    """Create a new customer scoped to the signed-in business."""
    enforce_plan_feature_limit(db, business=current_user.business, resource="customers")
    customer = create_customer(db, current_user=current_user, payload=payload)
    return CustomerResponse.model_validate(customer)


@router.post(
    "/verify-gstin",
    response_model=GstinVerifyResponse,
    summary="Verify a GSTIN and return extracted state/business details",
)
def verify_customer_gstin(
    payload: GstinVerifyRequest,
    _: User = Depends(get_current_user),
) -> GstinVerifyResponse:
    """Validate GSTIN format/checksum and fetch registered details if configured."""
    return verify_and_lookup_gstin(payload.gstin)


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get a customer by ID",
)
def read_customer(
    customer_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    """Return a customer owned by the signed-in business."""
    customer = get_owned_customer(
        db, business_id=current_user.business_id, customer_id=customer_id
    )
    return CustomerResponse.model_validate(customer)


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update a customer",
)
def update_customer_route(
    payload: CustomerUpdate,
    customer_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    """Update a customer owned by the signed-in business."""
    customer = update_customer(
        db,
        current_user=current_user,
        customer_id=customer_id,
        payload=payload,
    )
    return CustomerResponse.model_validate(customer)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer",
)
def delete_customer_route(
    customer_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a customer owned by the signed-in business."""
    delete_customer(db, current_user=current_user, customer_id=customer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
