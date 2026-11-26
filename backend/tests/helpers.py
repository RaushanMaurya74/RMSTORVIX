"""Shared test helpers for activating registered business accounts in pre-SaaS feature tests."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.saas import Subscription
from app.models.user import User


def activate_registered_account(client: TestClient, email: str) -> None:
    """Promote a newly registered test user + business to ACTIVE so feature routes unlock."""
    db: Session = getattr(client, "_db_session")
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    assert user is not None, f"Test user {email} not found"
    business = db.scalar(select(Business).where(Business.id == user.business_id))
    assert business is not None

    user.approval_status = "ACTIVE"
    user.is_active = True
    user.approved_at = now
    business.subscription_status = "ACTIVE"

    sub = db.scalar(select(Subscription).where(Subscription.business_id == business.id))
    if sub is None:
        sub = Subscription(
            business_id=business.id,
            plan_name="Test Active Plan",
            status="ACTIVE",
            starts_at=now,
            expires_at=now + timedelta(days=365),
        )
        db.add(sub)
    else:
        sub.status = "ACTIVE"
        sub.starts_at = now
        sub.expires_at = now + timedelta(days=365)

    db.commit()
