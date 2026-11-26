"""Protected Product / Service catalog CRUD endpoints."""

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_active_subscription_user, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductStockAdjustRequest,
    ProductUpdate,
)
from app.services.product_service import (
    adjust_product_stock,
    create_product,
    delete_product,
    get_owned_product,
    list_products,
    update_product,
)
from app.services.saas_service import enforce_plan_feature_limit

router = APIRouter(prefix="/products", tags=["Products & Services"])


@router.get(
    "",
    response_model=ProductListResponse,
    summary="List products and services for the authenticated business",
)
def read_products(
    q: str | None = Query(default=None, max_length=120),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductListResponse:
    """Search, filter, and paginate products/services owned by the signed-in business."""
    items, total, total_pages = list_products(
        db,
        business_id=current_user.business_id,
        q=q,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product or service",
)
def create_product_route(
    payload: ProductCreate,
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """Create a new catalog item scoped to the signed-in business."""
    enforce_plan_feature_limit(db, business=current_user.business, resource="products")
    product = create_product(db, current_user=current_user, payload=payload)
    return ProductResponse.model_validate(product)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a product or service by ID",
)
def read_product(
    product_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """Return a catalog item owned by the signed-in business."""
    product = get_owned_product(
        db, business_id=current_user.business_id, product_id=product_id
    )
    return ProductResponse.model_validate(product)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product or service",
)
def update_product_route(
    payload: ProductUpdate,
    product_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """Update a catalog item owned by the signed-in business."""
    product = update_product(
        db,
        current_user=current_user,
        product_id=product_id,
        payload=payload,
    )
    return ProductResponse.model_validate(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product or service",
)
def delete_product_route(
    product_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a catalog item owned by the signed-in business."""
    delete_product(db, current_user=current_user, product_id=product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{product_id}/adjust-stock",
    response_model=ProductResponse,
    summary="Adjust product inventory stock level",
)
def adjust_product_stock_route(
    payload: ProductStockAdjustRequest,
    product_id: int = Path(ge=1),
    current_user: User = Depends(get_active_subscription_user),
    db: Session = Depends(get_db),
) -> ProductResponse:
    """Apply a positive or negative stock delta with audit logging."""
    product = adjust_product_stock(
        db,
        current_user=current_user,
        product_id=product_id,
        payload=payload,
    )
    return ProductResponse.model_validate(product)
