"""Tests for Payments, Sales Reports, CSV Export, Audit Trail, and Isolation."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from tests.helpers import activate_registered_account


def _setup_invoice(
    client: TestClient,
    *,
    email: str,
    biz_name: str,
    customer_name: str = "Acme Client",
    unit_price: str = "200.00",
    tax_rate: str = "10.00",
    issue_immediately: bool = True,
    due_offset_days: int = 10,
) -> tuple[int, int]:
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Owner",
            "email": email,
            "password": "Password123!",
            "business_name": biz_name,
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, email)

    cust = client.post("/api/v1/customers", json={"name": customer_name})
    assert cust.status_code == 201
    cust_id = cust.json()["id"]

    today = date.today()
    inv = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": (today - timedelta(days=20)).isoformat()
            if due_offset_days < 0
            else today.isoformat(),
            "due_date": (today + timedelta(days=due_offset_days)).isoformat(),
            "issue_immediately": issue_immediately,
            "items": [
                {
                    "item_name": "Consulting",
                    "hsn_code": "998314",
                    "quantity": "1.00",
                    "unit_price": unit_price,
                    "tax_rate": tax_rate,
                }
            ],
        },
    )
    assert inv.status_code == 201
    return cust_id, inv.json()["id"]


def test_payments_and_reports_require_authentication(client: TestClient) -> None:
    """Unauthenticated callers receive 401 across payments and reports endpoints."""
    assert client.get("/api/v1/payments").status_code == 401
    assert client.post("/api/v1/payments", json={}).status_code == 401
    assert client.delete("/api/v1/payments/1").status_code == 401
    assert client.get("/api/v1/reports/summary").status_code == 401
    assert client.get("/api/v1/reports/invoices.csv").status_code == 401
    assert client.get("/api/v1/reports/audit").status_code == 401


def test_payment_lifecycle_partial_full_overpay_and_reversal(
    client: TestClient,
    db_session: Session,
) -> None:
    """Payments update invoice balance/status transactionally and reverse cleanly."""
    cust_id, draft_id = _setup_invoice(
        client,
        email="pay@biz.test",
        biz_name="Pay Biz",
        issue_immediately=False,
    )
    today = date.today().isoformat()

    # Draft invoice cannot accept payments
    draft_pay = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": draft_id,
            "amount": "50.00",
            "payment_date": today,
            "payment_method": "cash",
        },
    )
    assert draft_pay.status_code == 409

    # Issue invoice (total = 220.00)
    issued = client.post(f"/api/v1/invoices/{draft_id}/issue")
    assert issued.status_code == 200
    assert issued.json()["total_amount"] == "220.00"

    # Partial payment
    p1 = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": draft_id,
            "amount": "100.00",
            "payment_date": today,
            "payment_method": "bank_transfer",
            "reference": "WIRE-01",
        },
    )
    assert p1.status_code == 201
    p1_id = p1.json()["id"]

    inv_after_p1 = client.get(f"/api/v1/invoices/{draft_id}").json()
    assert inv_after_p1["status"] == "partially_paid"
    assert inv_after_p1["amount_paid"] == "100.00"
    assert inv_after_p1["balance_due"] == "120.00"

    # Overpayment rejected
    overpay = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": draft_id,
            "amount": "120.01",
            "payment_date": today,
            "payment_method": "upi",
        },
    )
    assert overpay.status_code == 409

    # Final payment settles invoice
    p2 = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": draft_id,
            "amount": "120.00",
            "payment_date": today,
            "payment_method": "upi",
            "reference": "UPI-99",
        },
    )
    assert p2.status_code == 201
    inv_after_p2 = client.get(f"/api/v1/invoices/{draft_id}").json()
    assert inv_after_p2["status"] == "paid"
    assert inv_after_p2["amount_paid"] == "220.00"
    assert inv_after_p2["balance_due"] == "0.00"

    # Filter payments by method
    upi_list = client.get("/api/v1/payments", params={"payment_method": "upi"})
    assert upi_list.status_code == 200
    assert upi_list.json()["total"] == 1
    assert upi_list.json()["items"][0]["reference"] == "UPI-99"

    # Reverse second payment -> restores partially_paid and 120.00 balance
    del_p2 = client.delete(f"/api/v1/payments/{p2.json()['id']}")
    assert del_p2.status_code == 204
    inv_restored = client.get(f"/api/v1/invoices/{draft_id}").json()
    assert inv_restored["status"] == "partially_paid"
    assert inv_restored["amount_paid"] == "100.00"
    assert inv_restored["balance_due"] == "120.00"

    # Reverse first payment -> restores issued and 220.00 balance
    assert client.delete(f"/api/v1/payments/{p1_id}").status_code == 204
    inv_unpaid = client.get(f"/api/v1/invoices/{draft_id}").json()
    assert inv_unpaid["status"] == "issued"
    assert inv_unpaid["amount_paid"] == "0.00"
    assert inv_unpaid["balance_due"] == "220.00"

    actions = set(
        db_session.scalars(
            select(AuditEvent.action).where(AuditEvent.entity_type == "payment")
        ).all()
    )
    assert {"payment.recorded", "payment.deleted"} <= actions


def test_reports_csv_injection_guard_audit_and_isolation(client: TestClient) -> None:
    """Reports, CSV export, and audit trail stay accurate and isolated per business."""
    _, inv_a1 = _setup_invoice(
        client,
        email="rep@alpha.test",
        biz_name="Alpha Reports",
        customer_name="=CMD('calc')",  # Tests CSV formula injection neutralization
        unit_price="100.00",
        tax_rate="10.00",
        due_offset_days=-5,  # Overdue
    )
    today = date.today().isoformat()
    pay_a = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": inv_a1,
            "amount": "40.00",
            "payment_date": today,
            "payment_method": "card",
        },
    )
    assert pay_a.status_code == 201
    pay_a_id = pay_a.json()["id"]

    # Invalid date range returns 422
    bad_dates = client.get(
        "/api/v1/reports/summary",
        params={"date_from": "2026-12-10", "date_to": "2026-12-01"},
    )
    assert bad_dates.status_code == 422

    summary = client.get("/api/v1/reports/summary")
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_invoices"] == 1
    assert s["overdue_count"] == 1
    assert s["total_billed"] == "110.00"
    assert s["total_cgst"] == "5.00"
    assert s["total_sgst"] == "5.00"
    assert s["total_igst"] == "0.00"
    assert s["total_tax"] == "10.00"
    assert s["total_paid_on_invoices"] == "40.00"
    assert s["total_outstanding"] == "70.00"
    assert s["total_collected_payments"] == "40.00"
    assert s["top_customers"][0]["total_billed"] == "110.00"
    assert s["hsn_summary"][0]["hsn_code"] == "998314"
    assert s["hsn_summary"][0]["total_tax"] == "10.00"

    csv_resp = client.get("/api/v1/reports/invoices.csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "'=CMD('calc')" in csv_resp.text
    assert "INV-1" in csv_resp.text

    audit_resp = client.get("/api/v1/reports/audit")
    assert audit_resp.status_code == 200
    assert audit_resp.json()["total"] >= 3
    assert "password_hash" not in audit_resp.text

    # Switch to Business B and verify complete isolation
    client.post("/api/v1/auth/logout")
    _setup_invoice(
        client,
        email="rep@beta.test",
        biz_name="Beta Reports",
        customer_name="Beta Buyer",
        unit_price="500.00",
        tax_rate="0.00",
    )

    assert (
        client.post(
            "/api/v1/payments",
            json={
                "invoice_id": inv_a1,
                "amount": "10.00",
                "payment_date": today,
                "payment_method": "cash",
            },
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/payments/{pay_a_id}").status_code == 404

    beta_summary = client.get("/api/v1/reports/summary").json()
    assert beta_summary["total_invoices"] == 1
    assert beta_summary["total_billed"] == "500.00"
    beta_csv = client.get("/api/v1/reports/invoices.csv").text
    assert "=CMD" not in beta_csv
    assert "Beta Buyer" in beta_csv
