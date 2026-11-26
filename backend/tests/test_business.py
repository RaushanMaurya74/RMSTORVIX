"""Tests for protected Business Profile routes and business scoping."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from tests.helpers import activate_registered_account


def test_business_endpoints_require_authentication(client: TestClient) -> None:
    """Unauthenticated callers must receive 401 for GET and PUT /api/v1/business."""
    assert client.get("/api/v1/business").status_code == 401
    assert (
        client.put(
            "/api/v1/business",
            json={
                "name": "Unauthorized Co",
                "currency_code": "USD",
                "invoice_prefix": "INV-",
                "next_invoice_number": 1,
            },
        ).status_code
        == 401
    )


def test_business_profile_update_validation_and_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    """Authenticated user can update their business profile and audit event is recorded."""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@northwind.test",
            "password": "Password123!",
            "business_name": "Northwind",
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, "jordan@northwind.test")
    business_id = reg.json()["business"]["id"]

    bad = client.put(
        "/api/v1/business",
        json={
            "name": "Northwind",
            "currency_code": "US",
            "invoice_prefix": "INV-",
            "next_invoice_number": 0,
        },
    )
    assert bad.status_code == 422

    updated = client.put(
        "/api/v1/business",
        json={
            "name": "Northwind Consulting",
            "legal_name": "Northwind Consulting LLC",
            "email": "billing@northwind.test",
            "phone": "+1-555-0199",
            "address_line1": "100 Main St",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country": "USA",
            "tax_id": "GST-998877",
            "currency_code": "inr",
            "invoice_prefix": "NW-",
            "next_invoice_number": 42,
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["id"] == business_id
    assert body["name"] == "Northwind Consulting"
    assert body["currency_code"] == "INR"
    assert body["invoice_prefix"] == "NW-"
    assert body["next_invoice_number"] == 42

    fetched = client.get("/api/v1/business")
    assert fetched.status_code == 200
    assert fetched.json()["tax_id"] == "GST-998877"

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.business_id == business_id,
            AuditEvent.action == "business.updated",
        )
    )
    assert audit is not None
    assert "currency_code" in audit.details_json["changed_fields"]


def test_business_profiles_are_isolated_across_accounts(client: TestClient) -> None:
    """User B's session only reads and updates User B's business, never User A's."""
    reg_a = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "User A",
            "email": "a@example.test",
            "password": "Password123!",
            "business_name": "Alpha Biz",
        },
    )
    assert reg_a.status_code == 201
    activate_registered_account(client, "a@example.test")
    biz_a_id = reg_a.json()["business"]["id"]

    client.post("/api/v1/auth/logout")

    reg_b = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "User B",
            "email": "b@example.test",
            "password": "Password123!",
            "business_name": "Beta Biz",
        },
    )
    assert reg_b.status_code == 201
    activate_registered_account(client, "b@example.test")
    biz_b_id = reg_b.json()["business"]["id"]
    assert biz_b_id != biz_a_id

    b_profile = client.get("/api/v1/business")
    assert b_profile.status_code == 200
    assert b_profile.json()["id"] == biz_b_id
    assert b_profile.json()["name"] == "Beta Biz"

    # Log back in as User A and verify Alpha Biz is untouched
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.test", "password": "Password123!"},
    )
    a_profile = client.get("/api/v1/business")
    assert a_profile.status_code == 200
    assert a_profile.json()["id"] == biz_a_id
    assert a_profile.json()["name"] == "Alpha Biz"


def test_business_bank_and_upi_validation(client: TestClient) -> None:
    """Bank details, IFSC code, and UPI ID validate and persist cleanly."""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Bank Owner",
            "email": "bank@biz.test",
            "password": "Password123!",
            "business_name": "Bank Biz",
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, "bank@biz.test")

    bad_ifsc = client.put(
        "/api/v1/business",
        json={
            "name": "Bank Biz",
            "currency_code": "INR",
            "invoice_prefix": "INV-",
            "next_invoice_number": 1,
            "bank_ifsc_code": "INVALID",
        },
    )
    assert bad_ifsc.status_code == 422

    bad_upi = client.put(
        "/api/v1/business",
        json={
            "name": "Bank Biz",
            "currency_code": "INR",
            "invoice_prefix": "INV-",
            "next_invoice_number": 1,
            "upi_id": "not-a-upi",
        },
    )
    assert bad_upi.status_code == 422

    good = client.put(
        "/api/v1/business",
        json={
            "name": "Bank Biz",
            "currency_code": "INR",
            "invoice_prefix": "INV-",
            "next_invoice_number": 1,
            "bank_account_holder": "Bank Biz LLP",
            "bank_name": "HDFC Bank",
            "bank_account_number": "9988776655",
            "bank_ifsc_code": "hdfc0001234",
            "bank_branch": "Pune",
            "upi_id": "bankbiz@hdfcbank",
        },
    )
    assert good.status_code == 200
    assert good.json()["bank_ifsc_code"] == "HDFC0001234"
    assert good.json()["upi_id"] == "bankbiz@hdfcbank"


def _make_image_bytes(fmt: str, size: tuple[int, int] = (240, 80)) -> bytes:
    import io
    from PIL import Image

    img = Image.new("RGBA" if fmt == "PNG" else "RGB", size, (23, 32, 51))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_business_visual_signature_upload_preview_pdf_and_isolation(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    """Visual signature upload validates images, isolates by business, and renders in PDF."""
    from datetime import date
    from app.core.config import Settings
    from app.services.pdf_service import generate_and_store_invoice_pdf
    from app.services.signature_service import (
        get_business_signature_bytes,
        load_signature_png_for_pdf,
        remove_business_signature,
        upload_business_signature,
    )

    sig_dir = tmp_path / "sigs"
    pdf_dir = tmp_path / "pdfs"
    test_settings = Settings(
        app_env="test",
        storage_signature_dir=str(sig_dir),
        storage_pdf_dir=str(pdf_dir),
        signature_max_bytes=100_000,
    )

    monkeypatch.setattr(
        "app.api.business.upload_business_signature",
        lambda db, *, current_user, file_bytes, content_type: upload_business_signature(
            db,
            current_user=current_user,
            file_bytes=file_bytes,
            content_type=content_type,
            settings=test_settings,
        ),
    )
    monkeypatch.setattr(
        "app.api.business.get_business_signature_bytes",
        lambda db, *, business_id: get_business_signature_bytes(
            db, business_id=business_id, settings=test_settings
        ),
    )
    monkeypatch.setattr(
        "app.api.business.remove_business_signature",
        lambda db, *, current_user: remove_business_signature(
            db, current_user=current_user, settings=test_settings
        ),
    )
    monkeypatch.setattr(
        "app.services.pdf_service.load_signature_png_for_pdf",
        lambda business: load_signature_png_for_pdf(business, settings=test_settings),
    )
    monkeypatch.setattr(
        "app.api.invoices.generate_and_store_invoice_pdf",
        lambda db, *, current_user, invoice_id: generate_and_store_invoice_pdf(
            db,
            current_user=current_user,
            invoice_id=invoice_id,
            settings=test_settings,
        ),
    )

    assert client.get("/api/v1/business/signature").status_code == 401

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Sig Owner",
            "email": "sig@biz.test",
            "password": "Password123!",
            "business_name": "Sig Biz",
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, "sig@biz.test")
    assert reg.json()["business"]["has_signature"] is False
    assert "signature_storage_key" not in reg.json()["business"]

    # Reject non-image bytes even if MIME says image/png
    bad_img = client.post(
        "/api/v1/business/signature",
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    assert bad_img.status_code == 422

    # Reject oversized image
    oversized = client.post(
        "/api/v1/business/signature",
        files={"file": ("big.png", b"x" * 100_001, "image/png")},
    )
    assert oversized.status_code == 422

    # Upload PNG signature
    png_bytes = _make_image_bytes("PNG", (300, 90))
    up1 = client.post(
        "/api/v1/business/signature",
        files={"file": ("sig.png", png_bytes, "image/png")},
    )
    assert up1.status_code == 200
    assert up1.json()["has_signature"] is True
    assert up1.json()["signature_enabled"] is True
    assert "signature_storage_key" not in up1.json()

    fetched = client.get("/api/v1/business/signature")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"

    # Replace with WebP signature + set placement to bottom_center
    webp_bytes = _make_image_bytes("WEBP", (220, 70))
    up2 = client.post(
        "/api/v1/business/signature",
        files={"file": ("sig.webp", webp_bytes, "image/webp")},
    )
    assert up2.status_code == 200
    assert client.get("/api/v1/business/signature").headers["content-type"] == "image/webp"

    upd = client.put(
        "/api/v1/business",
        json={
            "name": "Sig Biz",
            "currency_code": "INR",
            "invoice_prefix": "INV-",
            "next_invoice_number": 1,
            "signature_enabled": True,
            "signature_placement": "bottom_center",
        },
    )
    assert upd.status_code == 200
    assert upd.json()["signature_placement"] == "bottom_center"

    # Create invoice and verify PDF renders with WebP signature converted cleanly
    cust = client.post("/api/v1/customers", json={"name": "Sig Buyer"}).json()
    inv = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust["id"],
            "issue_date": date.today().isoformat(),
            "due_date": date.today().isoformat(),
            "issue_immediately": True,
            "items": [{"item_name": "Design", "quantity": "1", "unit_price": "100.00"}],
        },
    )
    assert inv.status_code == 201
    assert inv.json()["signature"]["has_signature"] is True
    assert inv.json()["signature"]["signature_placement"] == "bottom_center"

    pdf_resp = client.get(f"/api/v1/invoices/{inv.json()['id']}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF-")

    # Business B cannot access Business A's signature
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Other",
            "email": "other@sig.test",
            "password": "Password123!",
            "business_name": "Other Biz",
        },
    )
    activate_registered_account(client, "other@sig.test")
    assert client.get("/api/v1/business/signature").status_code == 404

    # Log back in as Business A and remove signature
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "sig@biz.test", "password": "Password123!"},
    )
    removed = client.delete("/api/v1/business/signature")
    assert removed.status_code == 200
    assert removed.json()["has_signature"] is False
    assert removed.json()["signature_enabled"] is False
    assert client.get("/api/v1/business/signature").status_code == 404


def test_business_logo_upload_replace_pdf_and_isolation(client: TestClient) -> None:
    """Logo endpoints validate uploads, enforce isolation, embed into PDFs, and delete cleanly."""
    assert client.get("/api/v1/business/logo").status_code == 401
    assert client.post("/api/v1/business/logo").status_code == 401
    assert client.put("/api/v1/business/logo").status_code == 401
    assert client.delete("/api/v1/business/logo").status_code == 401

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Logo Owner",
            "email": "logo@biz.test",
            "password": "Password123!",
            "business_name": "Logo Works Pvt Ltd",
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, "logo@biz.test")
    assert reg.json()["business"]["has_logo"] is False

    bad = client.post(
        "/api/v1/business/logo",
        files={"file": ("evil.svg", b"<svg></svg>", "image/svg+xml")},
    )
    assert bad.status_code == 422

    png_bytes = _make_image_bytes("PNG", (240, 100))
    up = client.post(
        "/api/v1/business/logo",
        files={"file": ("logo.png", png_bytes, "image/png")},
    )
    assert up.status_code == 200
    assert up.json()["has_logo"] is True
    assert "logo_storage_key" not in up.json()

    fetched = client.get("/api/v1/business/logo")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"

    # Replace via PUT using WebP
    webp_bytes = _make_image_bytes("WEBP", (180, 90))
    rep = client.put(
        "/api/v1/business/logo",
        files={"file": ("logo.webp", webp_bytes, "image/webp")},
    )
    assert rep.status_code == 200
    assert client.get("/api/v1/business/logo").headers["content-type"] == "image/webp"

    # Create invoice and verify logo summary + PDF generation
    cust = client.post("/api/v1/customers", json={"name": "Logo Buyer"}).json()
    inv = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust["id"],
            "issue_date": date.today().isoformat(),
            "due_date": date.today().isoformat(),
            "issue_immediately": True,
            "items": [{"item_name": "Brand Retainer", "quantity": "1", "unit_price": "500.00"}],
        },
    )
    assert inv.status_code == 201
    assert inv.json()["logo"]["has_logo"] is True

    pdf_resp = client.get(f"/api/v1/invoices/{inv.json()['id']}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF-")

    # Cross-business isolation: another business cannot see Business A's logo
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Other Logo",
            "email": "other@logo.test",
            "password": "Password123!",
            "business_name": "Other Logo Biz",
        },
    )
    activate_registered_account(client, "other@logo.test")
    assert client.get("/api/v1/business/logo").status_code == 404

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "logo@biz.test", "password": "Password123!"},
    )
    removed = client.delete("/api/v1/business/logo")
    assert removed.status_code == 200
    assert removed.json()["has_logo"] is False
    assert client.get("/api/v1/business/logo").status_code == 404


def test_invoice_theme_presets_custom_colors_validation_and_pdf(client: TestClient) -> None:
    """Theme/appearance endpoints require auth, validate hex colors, persist, and theme PDFs."""
    assert client.get("/api/v1/business/appearance").status_code == 401
    assert client.get("/api/v1/business/theme").status_code == 401
    assert client.put("/api/v1/business/theme", json={}).status_code == 401

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Theme Owner",
            "email": "theme@biz.test",
            "password": "Password123!",
            "business_name": "Chroma Studio",
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, "theme@biz.test")

    appearance = client.get("/api/v1/business/appearance")
    assert appearance.status_code == 200
    adata = appearance.json()
    assert len(adata["presets"]) >= 8
    assert adata["theme"]["preset"] == "classic_blue"

    # Reject invalid hex color
    bad_color = client.put(
        "/api/v1/business/theme",
        json={
            "preset": "custom",
            "primary_color": "not-a-color",
            "secondary_color": "#065F46",
            "accent_color": "#ECFDF5",
            "header_color": "#F0FDF4",
            "table_header_color": "#111827",
            "text_color": "#111827",
            "border_color": "#D1D5DB",
        },
    )
    assert bad_color.status_code == 422

    # Save dark table-header theme (Emerald + dark table header contrast check)
    saved = client.put(
        "/api/v1/business/theme",
        json={
            "preset": "emerald_green",
            "primary_color": "#059669",
            "secondary_color": "#065f46",
            "accent_color": "#ecfdf5",
            "header_color": "#f0fdf4",
            "table_header_color": "#064e3b",
            "text_color": "#14281d",
            "border_color": "#a7f3d0",
        },
    )
    assert saved.status_code == 200
    st = saved.json()["theme"]
    assert st["preset"] == "emerald_green"
    assert st["secondary_color"] == "#065F46"
    assert st["table_header_color"] == "#064E3B"

    cust = client.post("/api/v1/customers", json={"name": "Theme Buyer"}).json()
    inv = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": cust["id"],
            "issue_date": date.today().isoformat(),
            "due_date": date.today().isoformat(),
            "issue_immediately": True,
            "items": [{"item_name": "Theme Plan", "quantity": "2", "unit_price": "750.00"}],
        },
    )
    assert inv.status_code == 201
    assert inv.json()["theme"]["primary_color"] == "#059669"
    assert inv.json()["theme"]["table_header_color"] == "#064E3B"

    pdf_resp = client.get(f"/api/v1/invoices/{inv.json()['id']}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF-")

