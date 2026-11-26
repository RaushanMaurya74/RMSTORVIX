"""Append-only audit trail helper."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def record_audit_event(
    db: Session,
    *,
    business_id: int,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit event inside the caller's active database transaction."""
    event = AuditEvent(
        business_id=business_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details_json=details,
    )
    db.add(event)
    return event
