"""Tests for registration, login, logout, and session enforcement."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_session_token
from app.models.audit_event import AuditEvent
from app.models.session import UserSession
from app.models.user import User


def _register_payload(email: str = "owner@acme.test", business_name: str = "Acme Studio") -> dict:
    return {
        "full_name": "Alex Morgan",
        "email": email,
        "password": "StrongPassword123!",
        "business_name": business_name,
    }


def test_register_creates_user_business_session_and_audit_event(
    client: TestClient,
    db_session: Session,
) -> None:
    """Registration should create user + business + hashed session + audit event atomically."""
    resp = client.post("/api/v1/auth/register", json=_register_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "owner@acme.test"
    assert body["user"]["role"] == "owner"
    assert body["business"]["name"] == "Acme Studio"
    assert "password_hash" not in str(body)

    cookie_name = get_settings().session_cookie_name
    raw_token = client.cookies.get(cookie_name)
    assert raw_token

    stored_user = db_session.scalar(select(User).where(User.email == "owner@acme.test"))
    assert stored_user is not None
    assert stored_user.password_hash != "StrongPassword123!"
    assert stored_user.password_hash.startswith("scrypt$")

    stored_session = db_session.scalar(
        select(UserSession).where(UserSession.user_id == stored_user.id)
    )
    assert stored_session is not None
    assert stored_session.token_hash == hash_session_token(raw_token)
    assert stored_session.token_hash != raw_token

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.business_id == stored_user.business_id,
            AuditEvent.action == "user.registered",
        )
    )
    assert audit is not None


def test_register_rejects_duplicate_email_and_invalid_input(client: TestClient) -> None:
    """Duplicate email should return 409 and invalid payload should return 422."""
    first = client.post("/api/v1/auth/register", json=_register_payload())
    assert first.status_code == 201

    dup = client.post("/api/v1/auth/register", json=_register_payload())
    assert dup.status_code == 409

    bad = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "A",
            "email": "not-an-email",
            "password": "short",
            "business_name": "B",
        },
    )
    assert bad.status_code == 422


def test_login_logout_and_me_lifecycle(client: TestClient, db_session: Session) -> None:
    """Login sets cookie, /auth/me succeeds, and logout revokes session."""
    reg = client.post("/api/v1/auth/register", json=_register_payload())
    assert reg.status_code == 201

    # Logout first session
    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401

    # Wrong password returns generic 401
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@acme.test", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # Valid login issues working session
    good_login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@acme.test", "password": "StrongPassword123!"},
    )
    assert good_login.status_code == 200
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@acme.test"

    # Expired session is rejected
    cookie_name = get_settings().session_cookie_name
    raw_token = client.cookies.get(cookie_name)
    assert raw_token
    session_row = db_session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(raw_token))
    )
    assert session_row is not None
    session_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401
