"""Tests for invoice calculations, transactions, ownership, lifecycle, and PDF export."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.audit_event import AuditEvent
from app.services.invoice_service import calculate_invoice_totals, calculate_line_amounts
from app.services.pdf_service import generate_and_store_invoice_pdf
from app.models.user import User
from tests.helpers import activate_registered_account


def _register_and_seed(client: TestClient, email: str, biz_name: str) -> tuple[int, int]:
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

    cust = client.post(
        "/api/v1/customers",
        json={"name": "Acme Customer", "email": "billing@acme.test"},
    )
    assert cust.status_code == 201

    prod = client.post(
        "/api/v1/products",
        json={
            "name": "Engineering Hour",
            "unit": "hour",
            "unit_price": "100.00",
            "tax_rate": "18.00",
            "tax_label": "GST",
        },
    )
    assert prod.status_code == 201
    return cust.json()["id"], prod.json()["id"]


def test_server_invoice_calculation_rounding() -> None:
    """Line and header calculations should use exact ROUND_HALF_UP decimal math."""
    line1 = calculate_line_amounts(
        quantity=Decimal("2.50"),
        unit_price=Decimal("33.33"),
        discount_percent=Decimal("10.00"),
        tax_rate=Decimal("18.00"),
    )
    # 2.50 * 33.33 = 83.325 -> 83.33; 10% = 8.333 -> 8.33; taxable = 75.00; 18% = 13.50
    assert line1.line_subtotal == Decimal("83.33")
    assert line1.line_discount == Decimal("8.33")
    assert line1.line_tax == Decimal("13.50")
    assert line1.line_total == Decimal("88.50")

    line2 = calculate_line_amounts(
        quantity=Decimal("1.00"),
        unit_price=Decimal("50.00"),
        discount_percent=Decimal("0.00"),
        tax_rate=Decimal("5.00"),
    )
    totals = calculate_invoice_totals([line1, line2])
    assert totals.subtotal_amount == Decimal("133.33")
    assert totals.discount_amount == Decimal("8.33")
    assert totals.tax_amount == Decimal("16.00")
    assert totals.total_amount == Decimal("141.00")


def test_invoices_require_authentication(client: TestClient) -> None:
    """Unauthenticated callers receive 401 on all invoice and PDF endpoints."""
    assert client.get("/api/v1/invoices").status_code == 401
    assert client.post("/api/v1/invoices", json={}).status_code == 401
    assert client.get("/api/v1/invoices/1").status_code == 401
    assert client.put("/api/v1/invoices/1", json={}).status_code == 401
    assert client.post("/api/v1/invoices/1/issue").status_code == 401
    assert client.post("/api/v1/invoices/1/void").status_code == 401
    assert client.delete("/api/v1/invoices/1").status_code == 401
    assert client.get("/api/v1/invoices/1/pdf").status_code == 401
    assert client.get("/api/v1/invoices/1/qr").status_code == 401


def test_invoice_lifecycle_calculations_validation_and_customer_guard(
    client: TestClient,
    db_session: Session,
) -> None:
    """Draft creation, edit, issue, void, overdue filter, and customer delete guard work."""
    cust_id, prod_id = _register_and_seed(client, "inv@biz.test", "Invoice Biz")

    today = date.today()
    # Invalid due_date < issue_date rejected with 422
    bad_dates = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": (today - timedelta(days=1)).isoformat(),
            "items": [{"item_name": "Work", "quantity": "1", "unit_price": "10"}],
        },
    )
    assert bad_dates.status_code == 422

    # Create draft invoice
    create_resp = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=14)).isoformat(),
            "notes": "Thank you for your business.",
            "items": [
                {
                    "product_id": prod_id,
                    "item_name": "Engineering Hour",
                    "quantity": "3.00",
                    "unit_price": "100.00",
                    "discount_percent": "10.00",
                    "tax_rate": "18.00",
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    inv = create_resp.json()
    assert inv["invoice_number"] == "INV-1"
    assert inv["status"] == "draft"
    assert inv["subtotal_amount"] == "300.00"
    assert inv["discount_amount"] == "30.00"
    assert inv["tax_amount"] == "48.60"
    assert inv["total_amount"] == "318.60"
    assert inv["balance_due"] == "318.60"
    assert "pdf_storage_key" not in inv

    # Deleting a customer linked to an invoice must be blocked with 409
    assert client.delete(f"/api/v1/customers/{cust_id}").status_code == 409

    # Edit draft invoice
    upd_resp = client.put(
        f"/api/v1/invoices/{inv['id']}",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=7)).isoformat(),
            "items": [
                {
                    "item_name": "Fixed Retainer",
                    "quantity": "1.00",
                    "unit_price": "500.00",
                    "discount_percent": "0.00",
                    "tax_rate": "10.00",
                }
            ],
        },
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["total_amount"] == "550.00"

    # Issue invoice
    issued = client.post(f"/api/v1/invoices/{inv['id']}/issue")
    assert issued.status_code == 200
    assert issued.json()["status"] == "issued"
    assert issued.json()["issued_at"] is not None

    # Unpaid issued invoice CAN be edited (with modification history) while hard delete is blocked (409)
    edited_issued = client.put(
        f"/api/v1/invoices/{inv['id']}",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=7)).isoformat(),
            "gst_mode": "igst",
            "items": [
                {
                    "item_name": "Fixed Retainer",
                    "hsn_code": "998314",
                    "quantity": "1.00",
                    "unit_price": "600.00",
                    "discount_percent": "0.00",
                    "tax_rate": "18.00",
                }
            ],
        },
    )
    assert edited_issued.status_code == 200
    edited_body = edited_issued.json()
    assert edited_body["gst_type"] == "igst"
    assert edited_body["igst_amount"] == "108.00"
    assert edited_body["cgst_amount"] == "0.00"
    assert edited_body["total_amount"] == "708.00"
    assert edited_body["items"][0]["hsn_code"] == "998314"
    assert len(edited_body["modifications"]) >= 3

    assert client.delete(f"/api/v1/invoices/{inv['id']}").status_code == 409

    # Create a second overdue invoice directly issued
    overdue_resp = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": (today - timedelta(days=20)).isoformat(),
            "due_date": (today - timedelta(days=5)).isoformat(),
            "issue_immediately": True,
            "items": [{"item_name": "Late Item", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert overdue_resp.status_code == 201
    assert overdue_resp.json()["invoice_number"] == "INV-2"
    assert overdue_resp.json()["effective_status"] == "overdue"

    overdue_list = client.get("/api/v1/invoices", params={"status": "overdue"})
    assert overdue_list.status_code == 200
    assert overdue_list.json()["total"] == 1
    assert overdue_list.json()["items"][0]["invoice_number"] == "INV-2"

    # Void/cancel unpaid invoice with reason -> locks editing and preserves history
    voided = client.post(
        f"/api/v1/invoices/{inv['id']}/void",
        json={"reason": "Customer requested cancellation"},
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "void"
    assert voided.json()["balance_due"] == "0.00"
    assert voided.json()["cancellation_reason"] == "Customer requested cancellation"
    assert voided.json()["is_editable"] is False

    # Cancelled invoice cannot be edited
    assert (
        client.put(
            f"/api/v1/invoices/{inv['id']}",
            json={
                "customer_id": cust_id,
                "issue_date": today.isoformat(),
                "due_date": today.isoformat(),
                "items": [{"item_name": "Tamper", "quantity": "1", "unit_price": "1"}],
            },
        ).status_code
        == 409
    )

    actions = set(
        db_session.scalars(
            select(AuditEvent.action).where(AuditEvent.entity_type == "invoice")
        ).all()
    )
    assert {"invoice.created", "invoice.updated", "invoice.issued", "invoice.voided"} <= actions


def test_invoice_pdf_generation_and_business_isolation(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """PDF generation produces valid PDFs in managed storage and enforces ownership."""
    pdf_dir = tmp_path / "pdfs"
    monkeypatch.setattr(
        "app.api.invoices.generate_and_store_invoice_pdf",
        lambda db, *, current_user, invoice_id: generate_and_store_invoice_pdf(
            db,
            current_user=current_user,
            invoice_id=invoice_id,
            settings=Settings(app_env="test", storage_pdf_dir=str(pdf_dir)),
        ),
    )

    cust_a, _ = _register_and_seed(client, "a@pdf.test", "Alpha PDF")
    today = date.today()
    inv_a = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_a,
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=10)).isoformat(),
            "issue_immediately": True,
            "items": [
                {
                    "item_name": "Advisory — Q4",
                    "description": "Strategic review €500",
                    "quantity": "2",
                    "unit_price": "250.00",
                    "tax_rate": "10.00",
                }
            ],
        },
    )
    assert inv_a.status_code == 201
    inv_a_id = inv_a.json()["id"]

    pdf_resp = client.get(f"/api/v1/invoices/{inv_a_id}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-")

    stored_files = list(pdf_dir.rglob("*.pdf"))
    assert len(stored_files) == 1

    # Switch to Business B and verify complete isolation
    client.post("/api/v1/auth/logout")
    _register_and_seed(client, "b@pdf.test", "Beta PDF")

    assert client.get(f"/api/v1/invoices/{inv_a_id}").status_code == 404
    assert client.get(f"/api/v1/invoices/{inv_a_id}/pdf").status_code == 404
    assert client.post(f"/api/v1/invoices/{inv_a_id}/issue").status_code == 404
    assert client.post(f"/api/v1/invoices/{inv_a_id}/void").status_code == 404
    assert client.delete(f"/api/v1/invoices/{inv_a_id}").status_code == 404
    assert (
        client.post(
            "/api/v1/invoices",
            json={
                "customer_id": cust_a,
                "issue_date": today.isoformat(),
                "due_date": today.isoformat(),
                "items": [{"item_name": "Cross-tenant", "quantity": "1", "unit_price": "10"}],
            },
        ).status_code
        == 404
    )

    # Verify audit event logged for PDF download under Business A
    user_a = db_session.scalar(select(User).where(User.email == "a@pdf.test"))
    assert user_a is not None
    pdf_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.business_id == user_a.business_id,
            AuditEvent.action == "invoice.pdf_downloaded",
        )
    )
    assert pdf_audit is not None


def test_gst_auto_split_qr_generation_and_paid_edit_protection(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Verify state-based CGST/SGST vs IGST, bank+UPI QR endpoint, PDF refresh, and paid lock."""
    from app.services.pdf_service import refresh_stored_invoice_pdf

    pdf_dir = tmp_path / "pdfs_qr"
    monkeypatch.setattr(
        "app.api.invoices.generate_and_store_invoice_pdf",
        lambda db, *, current_user, invoice_id: generate_and_store_invoice_pdf(
            db,
            current_user=current_user,
            invoice_id=invoice_id,
            settings=Settings(app_env="test", storage_pdf_dir=str(pdf_dir)),
        ),
    )
    monkeypatch.setattr(
        "app.api.invoices.refresh_stored_invoice_pdf",
        lambda db, *, invoice: refresh_stored_invoice_pdf(
            db,
            invoice=invoice,
            settings=Settings(app_env="test", storage_pdf_dir=str(pdf_dir)),
        ),
    )

    cust_id, _ = _register_and_seed(client, "qr@biz.test", "QR Biz")
    # Configure business state + bank + UPI details
    biz_upd = client.put(
        "/api/v1/business",
        json={
            "name": "QR Biz",
            "state": "Maharashtra",
            "currency_code": "INR",
            "invoice_prefix": "INV-",
            "next_invoice_number": 1,
            "bank_account_holder": "QR Biz Pvt Ltd",
            "bank_name": "State Bank of India",
            "bank_account_number": "123456789012",
            "bank_ifsc_code": "sbin0001234",
            "bank_branch": "Mumbai Main",
            "upi_id": "qrbiz@sbi",
        },
    )
    assert biz_upd.status_code == 200
    assert biz_upd.json()["bank_ifsc_code"] == "SBIN0001234"

    # Update customer to same state -> auto CGST + SGST
    client.put(
        f"/api/v1/customers/{cust_id}",
        json={"name": "Acme Customer", "state": "Maharashtra"},
    )
    today = date.today()
    inv_intra = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=7)).isoformat(),
            "issue_immediately": True,
            "items": [
                {
                    "item_name": "GST Service",
                    "hsn_code": "998314",
                    "quantity": "1.00",
                    "unit_price": "100.00",
                    "tax_rate": "18.00",
                }
            ],
        },
    )
    assert inv_intra.status_code == 201
    inv_data = inv_intra.json()
    assert inv_data["gst_type"] == "cgst_sgst"
    assert inv_data["cgst_amount"] == "9.00"
    assert inv_data["sgst_amount"] == "9.00"
    assert inv_data["igst_amount"] == "0.00"
    assert inv_data["payment_qr_available"] is True
    assert "pa=qrbiz%40sbi" in inv_data["payment_uri"]
    assert "am=118.00" in inv_data["payment_uri"]

    # Generate initial PDF and verify QR PNG endpoint
    assert client.get(f"/api/v1/invoices/{inv_data['id']}/pdf").status_code == 200
    qr_resp = client.get(f"/api/v1/invoices/{inv_data['id']}/qr")
    assert qr_resp.status_code == 200
    assert qr_resp.headers["content-type"] == "image/png"
    assert qr_resp.content.startswith(b"\x89PNG")

    # Edit unpaid issued invoice -> PDF auto-refreshes
    upd = client.put(
        f"/api/v1/invoices/{inv_data['id']}",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=10)).isoformat(),
            "items": [
                {
                    "item_name": "GST Service Updated",
                    "hsn_code": "998314",
                    "quantity": "2.00",
                    "unit_price": "100.00",
                    "tax_rate": "18.00",
                }
            ],
        },
    )
    assert upd.status_code == 200
    assert upd.json()["has_pdf"] is True
    assert upd.json()["total_amount"] == "236.00"

    # Record partial payment -> invoice becomes protected from editing
    pay = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": inv_data["id"],
            "amount": "100.00",
            "payment_date": today.isoformat(),
            "payment_method": "upi",
        },
    )
    assert pay.status_code == 201

    # QR amount updates to remaining balance (136.00)
    refetched = client.get(f"/api/v1/invoices/{inv_data['id']}").json()
    assert "am=136.00" in refetched["payment_uri"]
    assert refetched["is_editable"] is False

    # Attempted edit on partially paid invoice blocked with 409
    assert (
        client.put(
            f"/api/v1/invoices/{inv_data['id']}",
            json={
                "customer_id": cust_id,
                "issue_date": today.isoformat(),
                "due_date": today.isoformat(),
                "items": [{"item_name": "Tamper", "quantity": "1", "unit_price": "10"}],
            },
        ).status_code
        == 409
    )

    # Full payment settles invoice -> QR is no longer available (404)
    pay2 = client.post(
        "/api/v1/payments",
        json={
            "invoice_id": inv_data["id"],
            "amount": "136.00",
            "payment_date": today.isoformat(),
            "payment_method": "upi",
        },
    )
    assert pay2.status_code == 201
    assert client.get(f"/api/v1/invoices/{inv_data['id']}/qr").status_code == 404

    # Different customer state -> auto IGST
    client.put(
        f"/api/v1/customers/{cust_id}",
        json={"name": "Acme Customer", "state": "Karnataka"},
    )
    inv_inter = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": today.isoformat(),
            "issue_immediately": True,
            "items": [
                {
                    "item_name": "Interstate Service",
                    "quantity": "1.00",
                    "unit_price": "100.00",
                    "tax_rate": "18.00",
                }
            ],
        },
    )
    assert inv_inter.status_code == 201
    assert inv_inter.json()["gst_type"] == "igst"
    assert inv_inter.json()["igst_amount"] == "18.00"
    assert inv_inter.json()["cgst_amount"] == "0.00"


def test_permanent_invoice_deletion_policy_db_cascade_and_isolation(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Draft & cancelled unpaid invoices delete cleanly from DB+disk; paid/active issued stay guarded."""
    from app.models.invoice import Invoice, InvoiceItem, InvoiceModification
    from app.services.invoice_service import delete_draft_invoice as real_delete_invoice

    pdf_dir = tmp_path / "pdfs_del"
    del_settings = Settings(app_env="test", storage_pdf_dir=str(pdf_dir))
    monkeypatch.setattr(
        "app.api.invoices.generate_and_store_invoice_pdf",
        lambda db, *, current_user, invoice_id: generate_and_store_invoice_pdf(
            db,
            current_user=current_user,
            invoice_id=invoice_id,
            settings=del_settings,
        ),
    )
    monkeypatch.setattr(
        "app.api.invoices.delete_draft_invoice",
        lambda db, *, current_user, invoice_id: real_delete_invoice(
            db,
            current_user=current_user,
            invoice_id=invoice_id,
            settings=del_settings,
        ),
    )

    # Unauthenticated delete rejected with 401
    assert client.delete("/api/v1/invoices/1").status_code == 401

    cust_id, prod_id = _register_and_seed(client, "del@inv.test", "Delete Safe Co")
    today = date.today()

    # 1. Draft invoice can be permanently deleted from DB
    draft_res = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": today.isoformat(),
            "items": [
                {
                    "product_id": prod_id,
                    "item_name": "Draft Line",
                    "quantity": "1.00",
                    "unit_price": "200.00",
                    "tax_rate": "18.00",
                }
            ],
        },
    )
    assert draft_res.status_code == 201
    draft_id = draft_res.json()["id"]
    assert draft_res.json()["is_deletable"] is True

    # Generate PDF for the draft, then permanently delete it
    assert client.get(f"/api/v1/invoices/{draft_id}/pdf").status_code == 200
    assert len(list(pdf_dir.rglob("*.pdf"))) == 1

    del_draft = client.delete(f"/api/v1/invoices/{draft_id}")
    assert del_draft.status_code == 204
    assert db_session.get(Invoice, draft_id) is None
    assert (
        db_session.scalars(select(InvoiceItem).where(InvoiceItem.invoice_id == draft_id)).all()
        == []
    )
    assert (
        db_session.scalars(
            select(InvoiceModification).where(InvoiceModification.invoice_id == draft_id)
        ).all()
        == []
    )
    assert list(pdf_dir.rglob("*.pdf")) == []

    # 2. Issued invoice cannot be hard-deleted while active, must be voided first, then permanent delete works
    issued_res = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": today.isoformat(),
            "issue_immediately": True,
            "items": [{"item_name": "Issued Work", "quantity": "1", "unit_price": "150.00"}],
        },
    )
    assert issued_res.status_code == 201
    issued_id = issued_res.json()["id"]
    assert issued_res.json()["is_deletable"] is False
    assert client.delete(f"/api/v1/invoices/{issued_id}").status_code == 409

    void_res = client.post(
        f"/api/v1/invoices/{issued_id}/void",
        json={"reason": "Entered by mistake"},
    )
    assert void_res.status_code == 200
    assert void_res.json()["is_deletable"] is True

    # Other business cannot delete Business A's invoice
    client.post("/api/v1/auth/logout")
    _register_and_seed(client, "other@del.test", "Other Del Co")
    assert client.delete(f"/api/v1/invoices/{issued_id}").status_code == 404

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "del@inv.test", "password": "Password123!"})
    del_void = client.delete(f"/api/v1/invoices/{issued_id}")
    assert del_void.status_code == 204
    assert db_session.get(Invoice, issued_id) is None

    # 3. Paid invoice cannot be permanently deleted (or even voided)
    paid_inv = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust_id,
            "issue_date": today.isoformat(),
            "due_date": today.isoformat(),
            "issue_immediately": True,
            "items": [{"item_name": "Paid Retainer", "quantity": "1", "unit_price": "300.00"}],
        },
    ).json()
    client.post(
        "/api/v1/payments",
        json={
            "invoice_id": paid_inv["id"],
            "amount": "100.00",
            "payment_date": today.isoformat(),
            "payment_method": "cash",
        },
    )
    paid_detail = client.get(f"/api/v1/invoices/{paid_inv['id']}").json()
    assert paid_detail["is_deletable"] is False
    assert client.delete(f"/api/v1/invoices/{paid_inv['id']}").status_code == 409

    deleted_audits = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "invoice.deleted")
    ).all()
    assert len(deleted_audits) >= 2
