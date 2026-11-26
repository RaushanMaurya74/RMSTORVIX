"""Product / Service catalog service scoped strictly to the authenticated business."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductStockAdjustRequest, ProductUpdate
from app.services.audit_service import record_audit_event
from app.services.pagination import paginate_select


def get_owned_product(db: Session, *, business_id: int, product_id: int) -> Product:
    """Fetch a product only if owned by the caller's business; otherwise raise 404."""
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == business_id,
        )
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product or service not found.",
        )
    return product


def list_products(
    db: Session,
    *,
    business_id: int,
    q: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int, int]:
    """List catalog items owned by the business with search, filter, and pagination."""
    stmt = select(Product).where(Product.business_id == business_id)

    if is_active is not None:
        stmt = stmt.where(Product.is_active.is_(is_active))

    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(term),
                Product.sku.ilike(term),
                Product.hsn_code.ilike(term),
                Product.description.ilike(term),
            )
        )

    stmt = stmt.order_by(Product.name.asc(), Product.id.asc())
    return paginate_select(db, stmt, page=page, page_size=page_size)


def create_product(
    db: Session,
    *,
    current_user: User,
    payload: ProductCreate,
) -> Product:
    """Create a product/service within the authenticated business and log audit event."""
    product = Product(
        business_id=current_user.business_id,
        **payload.model_dump(),
    )
    db.add(product)
    db.flush()

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="product.created",
        entity_type="product",
        entity_id=product.id,
        details={"name": product.name},
    )
    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session,
    *,
    current_user: User,
    product_id: int,
    payload: ProductUpdate,
) -> Product:
    """Update an owned product/service and append an audit event."""
    product = get_owned_product(
        db, business_id=current_user.business_id, product_id=product_id
    )
    update_data = payload.model_dump()
    changed_fields = [
        field for field, value in update_data.items() if getattr(product, field) != value
    ]
    for field, value in update_data.items():
        setattr(product, field, value)

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="product.updated",
        entity_type="product",
        entity_id=product.id,
        details={"changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(product)
    return product


def delete_product(
    db: Session,
    *,
    current_user: User,
    product_id: int,
) -> None:
    """Delete an owned product/service and append an audit event."""
    product = get_owned_product(
        db, business_id=current_user.business_id, product_id=product_id
    )
    product_name = product.name
    db.delete(product)

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="product.deleted",
        entity_type="product",
        entity_id=product_id,
        details={"name": product_name},
    )
    db.commit()


def adjust_product_stock(
    db: Session,
    *,
    current_user: User,
    product_id: int,
    payload: ProductStockAdjustRequest,
) -> Product:
    """Atomically increment or decrement stock_quantity while preventing negative balances."""
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.business_id == current_user.business_id)
        .with_for_update()
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product or service not found.",
        )

    prev_stock = Decimal(product.stock_quantity).quantize(Decimal("0.01"))
    delta = Decimal(payload.delta_quantity).quantize(Decimal("0.01"))
    new_stock = (prev_stock + delta).quantize(Decimal("0.01"))
    if new_stock < Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock ({prev_stock}) for adjustment of {delta}.",
        )

    product.stock_quantity = new_stock
    action = "stock.purchased" if delta > Decimal("0.00") else "stock.adjusted"
    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action=action,
        entity_type="product",
        entity_id=product.id,
        details={
            "name": product.name,
            "delta": str(delta),
            "previous_stock": str(prev_stock),
            "new_stock": str(new_stock),
            "reason": payload.reason,
        },
    )
    db.commit()
    db.refresh(product)
    return product
