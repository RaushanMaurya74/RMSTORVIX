"""Secure idempotent initial administrator seeding helper & CLI entry point."""

from pathlib import Path
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models.saas import AdminAuditLog, AdminUser, SaasSettings  # noqa: E402


def ensure_initial_admin(db: Session, settings: Settings | None = None) -> AdminUser | None:
    """Seed the initial super_admin strictly from env vars when admin_users is empty."""
    active_settings = settings or get_settings()

    existing_count = db.scalar(select(func.count(AdminUser.id))) or 0
    if existing_count > 0:
        return None

    admin_email = (active_settings.initial_admin_email or "").strip().lower()
    raw_password = active_settings.initial_admin_password.get_secret_value()
    if not admin_email or not raw_password:
        return None

    admin_user = AdminUser(
        email=admin_email,
        full_name=(active_settings.initial_admin_name or "RMSTORVIX Administrator").strip(),
        password_hash=hash_password(raw_password),
        role="super_admin",
        is_active=True,
        must_change_password=True,
    )
    db.add(admin_user)
    db.flush()

    settings_row = db.get(SaasSettings, 1)
    if settings_row is None:
        db.add(
            SaasSettings(
                id=1,
                enforce_subscription_expiry=active_settings.enforce_subscription_expiry,
                allow_self_activation=active_settings.allow_self_activation,
                notification_intervals_days=active_settings.notification_intervals_days,
                support_email=active_settings.support_email,
                support_phone=active_settings.support_phone,
                updated_by_admin_id=admin_user.id,
            )
        )

    db.add(
        AdminAuditLog(
            admin_user_id=admin_user.id,
            actor_email=admin_user.email,
            action="admin.initial_seeded",
            target_type="admin_user",
            target_id=admin_user.id,
            details_json={"role": admin_user.role, "must_change_password": True},
        )
    )
    db.commit()
    db.refresh(admin_user)
    return admin_user


def main() -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        seeded = ensure_initial_admin(db)
        if seeded is not None:
            print(f"Initial administrator seeded: {seeded.email}")
        else:
            print("Admin users already initialized or INITIAL_ADMIN_* env vars unset.")


if __name__ == "__main__":
    main()
