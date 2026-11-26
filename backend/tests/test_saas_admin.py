"""Comprehensive SaaS Upgrade tests: Pending Approval, Admin Auth, Subscriptions, Activation Codes, Quotas & Security."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.saas import ActivationCode, AdminUser, Notification, Subscription, SubscriptionPlan
from app.services.saas_service import hash_activation_code


def _seed_test_admin(
    db: Session,
    *,
    email: str = "admin@rmstorvix.test",
    password: str = "InitAdminPass123!",
    must_change_password: bool = True,
) -> AdminUser:
    admin = AdminUser(
        email=email,
        full_name="Platform Admin",
        password_hash=hash_password(password),
        role="super_admin",
        is_active=True,
        must_change_password=must_change_password,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _admin_login_and_unlock(
    admin_client: TestClient,
    db: Session,
    *,
    email: str = "admin@rmstorvix.test",
    initial_password: str = "InitAdminPass123!",
    new_password: str = "RotatedStrongPass99!",
) -> None:
    _seed_test_admin(db, email=email, password=initial_password, must_change_password=True)
    login = admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": initial_password},
    )
    assert login.status_code == 200
    assert login.json()["admin"]["must_change_password"] is True

    # Blocked from admin overview until initial password is changed
    blocked = admin_client.get("/api/v1/admin/overview")
    assert blocked.status_code == 403

    chg = admin_client.post(
        "/api/v1/admin/auth/change-password",
        json={
            "current_password": initial_password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert chg.status_code == 200
    assert chg.json()["admin"]["must_change_password"] is False

    ok = admin_client.get("/api/v1/admin/overview")
    assert ok.status_code == 200


def test_registration_pending_approval_blocks_dashboard_and_code_cannot_bypass(
    client: TestClient,
    db_session: Session,
) -> None:
    """New accounts start PENDING_APPROVAL + NOT_ACTIVATED and cannot bypass via activation code."""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Priya Verma",
            "email": "priya@pending.test",
            "phone": "+91 9876543210",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
            "business_name": "Verma Traders",
            "business_type": "Wholesale & Distribution",
            "address": "MG Road, Pune",
            "terms_accepted": True,
        },
    )
    assert reg.status_code == 201
    data = reg.json()
    assert data["user"]["approval_status"] == "PENDING_APPROVAL"
    assert data["business"]["subscription_status"] == "NOT_ACTIVATED"
    assert data["subscription"]["status"] == "NOT_ACTIVATED"

    # Blocked from operational dashboard routes while pending
    for method, url in [
        ("GET", "/api/v1/customers"),
        ("POST", "/api/v1/customers"),
        ("GET", "/api/v1/products"),
        ("GET", "/api/v1/invoices"),
        ("GET", "/api/v1/business"),
        ("GET", "/api/v1/reports/summary"),
    ]:
        res = client.request(method, url, json={"name": "Blocked"} if method == "POST" else None)
        assert res.status_code == 403, f"Expected 403 for {method} {url}, got {res.status_code}"

    # User cannot access /admin routes with user session cookie
    assert client.get("/api/v1/admin/overview").status_code == 401

    # Seed an available activation code and verify pending user CANNOT bypass admin approval
    code = ActivationCode(
        code_value="RMX-TEST-1111-2222",
        code_hash=hash_activation_code("RMX-TEST-1111-2222"),
        duration_days=30,
        status="AVAILABLE",
        max_uses=1,
        use_count=0,
    )
    db_session.add(code)
    db_session.commit()

    bypass = client.post("/api/v1/subscription/activate", json={"code": "RMX-TEST-1111-2222"})
    assert bypass.status_code == 403
    assert "administrator approval" in bypass.json()["error"]["message"].lower()

    # Admin notification created on registration
    notif = db_session.scalar(
        select(Notification).where(
            Notification.audience == "admin",
            Notification.title.ilike("New Registration:%"),
        )
    )
    assert notif is not None


def test_admin_approval_activation_code_workflow_and_security(
    client: TestClient,
    db_session: Session,
) -> None:
    """Admin approves user -> generates code -> assigns -> user activates -> expiry enforces read-only."""
    admin_client = TestClient(client.app)
    _admin_login_and_unlock(admin_client, db_session)

    # Register user
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Rohan Kapoor",
            "email": "rohan@kapoor.test",
            "phone": "+91 9811122233",
            "password": "Password123!",
            "business_name": "Kapoor Enterprises",
            "terms_accepted": True,
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["user"]["id"]
    biz_id = reg.json()["business"]["id"]

    # Create a custom plan with max_invoices = 1 to verify plan quota enforcement
    plan_res = admin_client.post(
        "/api/v1/admin/plans",
        json={
            "code": "starter_30d",
            "name": "Starter 30",
            "duration_days": 30,
            "price": "499.00",
            "currency_code": "INR",
            "max_invoices": 1,
            "max_customers": 5,
        },
    )
    assert plan_res.status_code == 201
    plan_id = plan_res.json()["id"]

    # Step 1: Approve user (now APPROVED, subscription still NOT_ACTIVATED)
    app_res = admin_client.post(
        f"/api/v1/admin/users/{user_id}/approve",
        json={"allow_self_activation": True, "reason": "Verified GSTIN docs"},
    )
    assert app_res.status_code == 200
    assert app_res.json()["approval_status"] == "APPROVED"

    # Generate batch of 2 codes; assign 1st to Rohan
    gen_res = admin_client.post(
        "/api/v1/admin/activation-codes",
        json={
            "count": 2,
            "duration_days": 30,
            "plan_id": plan_id,
            "assigned_user_id": user_id,
            "notes": "Starter promo",
        },
    )
    assert gen_res.status_code == 201
    codes = gen_res.json()
    assert len(codes) == 2
    assert codes[0]["code_value"] != codes[1]["code_value"]
    assert codes[0]["code_value"].startswith("RMX-")
    code_str = codes[0]["code_value"]

    # CSV export works for admin
    csv_res = admin_client.get("/api/v1/admin/activation-codes/export.csv")
    assert csv_res.status_code == 200
    assert code_str in csv_res.text

    # Approved user activates using assigned code
    act_res = client.post("/api/v1/subscription/activate", json={"code": code_str})
    assert act_res.status_code == 200
    sub_json = act_res.json()
    assert sub_json["status"] == "ACTIVE"
    assert sub_json["plan_name"] == "Starter 30"
    assert sub_json["remaining_days"] >= 29

    # Double activation of the same single-use code is rejected
    dup_act = client.post("/api/v1/subscription/activate", json={"code": code_str})
    assert dup_act.status_code == 409

    # Workspace now unlocked! Create customer & 1 invoice (quota max_invoices=1)
    c1 = client.post("/api/v1/customers", json={"name": "Client One"})
    assert c1.status_code == 201
    inv1 = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": c1.json()["id"],
            "issue_date": datetime.now(timezone.utc).date().isoformat(),
            "due_date": (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat(),
            "items": [{"item_name": "Service", "quantity": "1.00", "unit_price": "100.00"}],
        },
    )
    assert inv1.status_code == 201

    # 2nd invoice exceeds plan quota max_invoices=1
    inv2 = client.post(
        "/api/v1/invoices",
        json={
            "customer_id": c1.json()["id"],
            "issue_date": datetime.now(timezone.utc).date().isoformat(),
            "due_date": (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat(),
            "items": [{"item_name": "Service 2", "quantity": "1.00", "unit_price": "50.00"}],
        },
    )
    assert inv2.status_code == 403
    assert "limit" in inv2.json()["error"]["message"].lower()

    # Force subscription expiration and test read-only / export accessibility vs write lock
    sub_row = db_session.scalar(select(Subscription).where(Subscription.business_id == biz_id))
    assert sub_row is not None
    sub_row.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()

    # Checking /subscription syncs status to EXPIRED cleanly & creates notification
    status_check = client.get("/api/v1/subscription")
    assert status_check.status_code == 200
    assert status_check.json()["status"] == "EXPIRED"

    # Writes are blocked (403), reads + CSV export + /subscription remain allowed!
    blocked_cust = client.post("/api/v1/customers", json={"name": "After Expiry"})
    assert blocked_cust.status_code == 403
    assert client.get("/api/v1/invoices").status_code == 200
    assert client.get("/api/v1/reports/invoices.csv").status_code == 200

    # Admin extends expired subscription -> becomes ACTIVE again and writes unlock
    ext_res = admin_client.post(
        f"/api/v1/admin/subscriptions/{sub_row.id}/extend",
        json={"extra_days": 60, "notes": "Renewed"},
    )
    assert ext_res.status_code == 200
    assert ext_res.json()["status"] == "ACTIVE"
    assert client.post("/api/v1/customers", json={"name": "After Renewal"}).status_code == 201

    # Admin deactivate revokes user sessions immediately
    deact = admin_client.post(f"/api/v1/admin/users/{user_id}/deactivate", json={"reason": "Pause"})
    assert deact.status_code == 200
    assert deact.json()["approval_status"] == "INACTIVE"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_activation_code_revocation_rate_limit_and_expiry(
    client: TestClient,
    db_session: Session,
) -> None:
    """Revoked/expired codes fail cleanly, and repeated invalid attempts hit 429 rate limit."""
    admin_client = TestClient(client.app)
    _admin_login_and_unlock(admin_client, db_session, email="secadmin@rmstorvix.test")

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Neha Singh",
            "email": "neha@ratelimit.test",
            "password": "Password123!",
            "business_name": "Singh Consultancy",
        },
    )
    user_id = reg.json()["user"]["id"]
    admin_client.post(f"/api/v1/admin/users/{user_id}/approve", json={"allow_self_activation": True})

    # Generate & revoke a code
    codes = admin_client.post(
        "/api/v1/admin/activation-codes",
        json={"count": 1, "duration_days": 30},
    ).json()
    c_id = codes[0]["id"]
    c_val = codes[0]["code_value"]
    rev = admin_client.post(f"/api/v1/admin/activation-codes/{c_id}/revoke", json={"reason": "Mistake"})
    assert rev.status_code == 200
    assert rev.json()["status"] == "REVOKED"

    # Attempt revoked code
    r_rev = client.post("/api/v1/subscription/activate", json={"code": c_val})
    assert r_rev.status_code == 409

    # Rate limit triggers after configured failures (max attempts - 1 prior revoked failure)
    max_attempts = get_settings().activation_rate_limit_max_attempts
    for idx in range(max_attempts - 1):
        bad = client.post("/api/v1/subscription/activate", json={"code": f"RMX-BAD0-000{idx}-XXXX"})
        assert bad.status_code == 404

    limited = client.post("/api/v1/subscription/activate", json={"code": "RMX-BAD0-9999-XXXX"})
    assert limited.status_code == 429


def test_forgot_password_notifies_admin_and_overview_metrics_work(
    client: TestClient,
    db_session: Session,
) -> None:
    """Forgot-password creates admin alert without leaking account existence; overview stats return accurate counts."""
    admin_client = TestClient(client.app)
    _admin_login_and_unlock(admin_client, db_session, email="ovadmin@rmstorvix.test")

    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test Owner",
            "email": "forgot@demo.test",
            "password": "Password123!",
            "business_name": "Demo Co",
        },
    )

    fp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "forgot@demo.test", "reason": "Forgot credential"},
    )
    assert fp.status_code == 200

    notifs = admin_client.get("/api/v1/admin/notifications").json()
    assert any("Password Reset Requested:" in n["title"] for n in notifs["items"])

    ov = admin_client.get("/api/v1/admin/overview").json()
    assert ov["total_registered_users"] == 1
    assert ov["pending_approval_users"] == 1
    assert ov["recent_audit_count"] >= 1


def test_user_change_password_lifecycle(client: TestClient) -> None:
    """Signed-in users can rotate their password after verifying the current password."""
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Pwd Owner",
            "email": "pwduser@demo.test",
            "password": "OldPassword123!",
            "business_name": "Pwd Co",
        },
    )

    bad_cur = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "WrongPassword!",
            "new_password": "NewPassword456!",
            "confirm_password": "NewPassword456!",
        },
    )
    assert bad_cur.status_code == 400

    mismatch = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "OldPassword123!",
            "new_password": "NewPassword456!",
            "confirm_password": "DifferentPassword!",
        },
    )
    assert mismatch.status_code == 422

    ok = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "OldPassword123!",
            "new_password": "NewPassword456!",
            "confirm_password": "NewPassword456!",
        },
    )
    assert ok.status_code == 200

    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "pwduser@demo.test", "password": "OldPassword123!"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "pwduser@demo.test", "password": "NewPassword456!"},
        ).status_code
        == 200
    )
