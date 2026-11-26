"""Tests for Product / Service catalog CRUD, decimal validation, and ownership."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from tests.helpers import activate_registered_account


def _register(client: TestClient, email: str, business: str) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Owner",
            "email": email,
            "password": "Password123!",
            "business_name": business,
        },
    )
    assert resp.status_code == 201
    activate_registered_account(client, email)


def test_products_require_authentication(client: TestClient) -> None:
    """Unauthenticated callers receive 401 across product endpoints."""
    assert client.get("/api/v1/products").status_code == 401
    assert (
        client.post("/api/v1/products", json={"name": "Consulting", "unit_price": "100.00"})
        .status_code
        == 401
    )
    assert client.get("/api/v1/products/1").status_code == 401
    assert (
        client.put("/api/v1/products/1", json={"name": "Consulting", "unit_price": "100.00"})
        .status_code
        == 401
    )
    assert client.delete("/api/v1/products/1").status_code == 401


def test_product_crud_validation_search_and_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    """Authenticated user can create, filter, update, and delete catalog items."""
    _register(client, "owner@prod.test", "Prod Biz")

    bad_price = client.post(
        "/api/v1/products",
        json={"name": "Invalid Item", "unit_price": "-5.00", "tax_rate": "10.00"},
    )
    assert bad_price.status_code == 422

    bad_tax = client.post(
        "/api/v1/products",
        json={"name": "Invalid Tax", "unit_price": "50.00", "tax_rate": "120.00"},
    )
    assert bad_tax.status_code == 422

    r1 = client.post(
        "/api/v1/products",
        json={
            "name": "Web Development",
            "sku": "SRV-WEB",
            "description": "Hourly engineering",
            "unit": "hour",
            "unit_price": "125.50",
            "tax_rate": "18.00",
            "tax_label": "GST",
            "is_active": True,
        },
    )
    assert r1.status_code == 201
    item_id = r1.json()["id"]
    assert r1.json()["unit_price"] == "125.50"
    assert r1.json()["tax_rate"] == "18.00"

    r2 = client.post(
        "/api/v1/products",
        json={
            "name": "Legacy Retainer",
            "sku": "RET-01",
            "unit_price": "500.00",
            "tax_rate": "0.00",
            "is_active": False,
        },
    )
    assert r2.status_code == 201

    search = client.get("/api/v1/products", params={"q": "SRV-WEB", "is_active": True})
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["name"] == "Web Development"

    updated = client.put(
        f"/api/v1/products/{item_id}",
        json={
            "name": "Web Architecture",
            "sku": "SRV-WEB",
            "unit": "hour",
            "unit_price": "150.00",
            "tax_rate": "18.00",
            "tax_label": "GST",
            "is_active": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["unit_price"] == "150.00"

    deleted = client.delete(f"/api/v1/products/{item_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/products/{item_id}").status_code == 404

    actions = set(
        db_session.scalars(
            select(AuditEvent.action).where(AuditEvent.entity_type == "product")
        ).all()
    )
    assert {"product.created", "product.updated", "product.deleted"} <= actions


def test_products_are_isolated_between_businesses(client: TestClient) -> None:
    """Business B cannot read, update, or delete Business A's products."""
    _register(client, "a@prodiso.test", "Biz A")
    created = client.post(
        "/api/v1/products",
        json={"name": "Secret Package", "unit_price": "999.00"},
    )
    assert created.status_code == 201
    prod_id = created.json()["id"]

    client.post("/api/v1/auth/logout")
    _register(client, "b@prodiso.test", "Biz B")

    assert client.get("/api/v1/products").json()["total"] == 0
    assert client.get(f"/api/v1/products/{prod_id}").status_code == 404
    assert (
        client.put(
            f"/api/v1/products/{prod_id}",
            json={"name": "Hijacked", "unit_price": "1.00"},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/products/{prod_id}").status_code == 404


def test_product_hsn_purchase_selling_and_stock_validation(client: TestClient) -> None:
    """Product HSN code, purchase/selling price, and stock quantity validate and search."""
    _register(client, "hsn@prod.test", "HSN Biz")

    bad_hsn = client.post(
        "/api/v1/products",
        json={"name": "Bad HSN", "hsn_code": "12A", "unit_price": "10.00"},
    )
    assert bad_hsn.status_code == 422

    created = client.post(
        "/api/v1/products",
        json={
            "name": "Thermal Printer",
            "sku": "PRT-01",
            "hsn_code": "844332",
            "purchase_price": "4500.00",
            "selling_price": "5999.00",
            "tax_rate": "18.00",
            "stock_quantity": "15.00",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["hsn_code"] == "844332"
    assert body["purchase_price"] == "4500.00"
    assert body["unit_price"] == "5999.00"
    assert body["selling_price"] == "5999.00"
    assert body["stock_quantity"] == "15.00"

    by_hsn = client.get("/api/v1/products", params={"q": "844332"})
    assert by_hsn.status_code == 200
    assert by_hsn.json()["total"] == 1
    assert by_hsn.json()["items"][0]["name"] == "Thermal Printer"


def test_product_stock_adjustment_movement_and_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    """Stock purchase/adjustment delta updates stock atomically and prevents negative balances."""
    _register(client, "stock@prod.test", "Stock Biz")

    created = client.post(
        "/api/v1/products",
        json={"name": "Paper Roll", "unit_price": "120.00", "stock_quantity": "10.00"},
    )
    assert created.status_code == 201
    prod_id = created.json()["id"]

    added = client.post(
        f"/api/v1/products/{prod_id}/adjust-stock",
        json={"delta_quantity": "15.00", "reason": "Supplier PO #102"},
    )
    assert added.status_code == 200
    assert added.json()["stock_quantity"] == "25.00"

    # Deduction exceeding current stock is rejected cleanly (409)
    over = client.post(
        f"/api/v1/products/{prod_id}/adjust-stock",
        json={"delta_quantity": "-30.00", "reason": "Invalid writeoff"},
    )
    assert over.status_code == 409

    # Valid write-off deduction works and logs stock.adjusted
    deducted = client.post(
        f"/api/v1/products/{prod_id}/adjust-stock",
        json={"delta_quantity": "-5.00", "reason": "Damaged unit"},
    )
    assert deducted.status_code == 200
    assert deducted.json()["stock_quantity"] == "20.00"

    # Audit events recorded cleanly for purchase & write-off
    audit_purchase = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "product",
            AuditEvent.entity_id == prod_id,
            AuditEvent.action == "stock.purchased",
        )
    )
    assert audit_purchase is not None
    assert audit_purchase.details_json is not None
    assert audit_purchase.details_json["new_stock"] == "25.00"

    audit_adjust = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "product",
            AuditEvent.entity_id == prod_id,
            AuditEvent.action == "stock.adjusted",
        )
    )
    assert audit_adjust is not None
    assert audit_adjust.details_json is not None
    assert audit_adjust.details_json["new_stock"] == "20.00"
