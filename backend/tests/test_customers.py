"""Tests for Customer CRUD, search/filtering/pagination, validation, and ownership."""

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


def test_customers_require_authentication(client: TestClient) -> None:
    """Unauthenticated callers receive 401 across customer endpoints."""
    assert client.get("/api/v1/customers").status_code == 401
    assert client.post("/api/v1/customers", json={"name": "Acme"}).status_code == 401
    assert client.get("/api/v1/customers/1").status_code == 401
    assert client.put("/api/v1/customers/1", json={"name": "Acme"}).status_code == 401
    assert client.delete("/api/v1/customers/1").status_code == 401


def test_customer_crud_search_pagination_and_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    """Authenticated user can create, search, filter, paginate, update, and delete customers."""
    _register(client, "owner@cust.test", "Cust Biz")

    bad = client.post("/api/v1/customers", json={"name": "A", "email": "bad-email"})
    assert bad.status_code == 422

    created_ids = []
    for name, company, email, active in [
        ("Alice Johnson", "Alpha Co", "alice@alpha.test", True),
        ("Bob Smith", "Beta Ltd", "bob@beta.test", True),
        ("Charlie Inactive", "Gamma Inc", "charlie@gamma.test", False),
    ]:
        r = client.post(
            "/api/v1/customers",
            json={
                "name": name,
                "company_name": company,
                "email": email,
                "is_active": active,
            },
        )
        assert r.status_code == 201
        created_ids.append(r.json()["id"])

    # Pagination
    page1 = client.get("/api/v1/customers", params={"page": 1, "page_size": 2})
    assert page1.status_code == 200
    assert page1.json()["total"] == 3
    assert page1.json()["total_pages"] == 2
    assert len(page1.json()["items"]) == 2

    # Search and active filter
    search = client.get("/api/v1/customers", params={"q": "beta", "is_active": True})
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["name"] == "Bob Smith"

    inactive = client.get("/api/v1/customers", params={"is_active": False})
    assert inactive.status_code == 200
    assert inactive.json()["total"] == 1
    assert inactive.json()["items"][0]["name"] == "Charlie Inactive"

    # Read & Update
    target_id = created_ids[0]
    fetched = client.get(f"/api/v1/customers/{target_id}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "alice@alpha.test"

    updated = client.put(
        f"/api/v1/customers/{target_id}",
        json={"name": "Alice Updated", "city": "Denver", "is_active": True},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Alice Updated"
    assert updated.json()["city"] == "Denver"

    # Delete
    deleted = client.delete(f"/api/v1/customers/{target_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/customers/{target_id}").status_code == 404

    actions = set(
        db_session.scalars(
            select(AuditEvent.action).where(AuditEvent.entity_type == "customer")
        ).all()
    )
    assert {"customer.created", "customer.updated", "customer.deleted"} <= actions


def test_customers_are_isolated_between_businesses(client: TestClient) -> None:
    """Business B cannot read, modify, or delete Business A's customers."""
    _register(client, "a@iso.test", "Biz A")
    created = client.post("/api/v1/customers", json={"name": "Private Client"})
    assert created.status_code == 201
    cust_id = created.json()["id"]

    client.post("/api/v1/auth/logout")
    _register(client, "b@iso.test", "Biz B")

    assert client.get("/api/v1/customers").json()["total"] == 0
    assert client.get(f"/api/v1/customers/{cust_id}").status_code == 404
    assert (
        client.put(f"/api/v1/customers/{cust_id}", json={"name": "Hijacked"}).status_code
        == 404
    )
    assert client.delete(f"/api/v1/customers/{cust_id}").status_code == 404


def test_gstin_verification_checksum_and_external_lookup(
    client: TestClient,
    monkeypatch,
) -> None:
    """GSTIN endpoint validates format/checksum, extracts state, and supports external lookup."""
    from app.core.config import Settings
    from app.services.gstin_service import compute_gstin_check_char, verify_and_lookup_gstin

    assert (
        client.post("/api/v1/customers/verify-gstin", json={"gstin": "27AAACP1234A1Z5"})
        .status_code
        == 401
    )

    _register(client, "gstin@cust.test", "GSTIN Biz")

    prefix14 = "27AAACP1234A1Z"
    valid_gstin = prefix14 + compute_gstin_check_char(prefix14)
    wrong_char = "0" if valid_gstin[-1] != "0" else "1"
    bad_checksum_gstin = prefix14 + wrong_char

    ok_resp = client.post(
        "/api/v1/customers/verify-gstin",
        json={"gstin": valid_gstin.lower()},
    )
    assert ok_resp.status_code == 200
    ok_body = ok_resp.json()
    assert ok_body["valid"] is True
    assert ok_body["checksum_valid"] is True
    assert ok_body["state"] == "Maharashtra"
    assert ok_body["country"] == "India"
    assert ok_body["pan"] == "AAACP1234A"

    bad_resp = client.post(
        "/api/v1/customers/verify-gstin",
        json={"gstin": bad_checksum_gstin},
    )
    assert bad_resp.status_code == 200
    assert bad_resp.json()["valid"] is False
    assert bad_resp.json()["checksum_valid"] is False

    # Saving customer with gstin_verified=True rejects invalid GSTIN
    rejected_cust = client.post(
        "/api/v1/customers",
        json={"name": "Bad GST Co", "tax_id": bad_checksum_gstin, "gstin_verified": True},
    )
    assert rejected_cust.status_code == 422

    # Saving customer with valid verified GSTIN succeeds
    saved_cust = client.post(
        "/api/v1/customers",
        json={
            "name": "Verified Co",
            "tax_id": valid_gstin,
            "gstin_verified": True,
            "state": "Maharashtra",
            "country": "India",
        },
    )
    assert saved_cust.status_code == 201
    assert saved_cust.json()["gstin_verified"] is True

    # Test external API response extraction when GSTIN_API_URL is configured
    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "data": {
                    "tradeNam": "ACME INDIA PVT LTD",
                    "pradr": {
                        "addr": {
                            "bno": "101",
                            "st": "MG Road",
                            "loc": "Fort",
                            "dst": "Mumbai",
                            "stcd": "Maharashtra",
                            "pncd": "400001",
                        }
                    },
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResp()

    monkeypatch.setattr("app.services.gstin_service.httpx.Client", FakeClient)
    ext = verify_and_lookup_gstin(
        valid_gstin,
        settings=Settings(app_env="test", gstin_api_url="https://api.example.test/gstin/{gstin}"),
    )
    assert ext.valid is True
    assert ext.lookup_source == "external_api"
    assert ext.company_name == "ACME INDIA PVT LTD"
    assert ext.city == "Mumbai"
    assert ext.postal_code == "400001"
