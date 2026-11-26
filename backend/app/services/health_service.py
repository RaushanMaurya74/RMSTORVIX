"""Service layer for application and database health verification."""

from datetime import datetime, timezone

from sqlalchemy import Engine

from app.core.config import Settings, get_settings
from app.db.session import check_database_connection
from app.schemas.health import DatabaseHealth, HealthResponse


def get_system_health(
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> HealthResponse:
    """Evaluate API readiness and PostgreSQL connectivity safely."""
    active_settings = settings or get_settings()
    is_connected, latency_ms, message = check_database_connection(engine=engine)

    return HealthResponse(
        status="ok" if is_connected else "degraded",
        service=active_settings.app_name,
        environment=active_settings.app_env,
        version=active_settings.app_version,
        timestamp=datetime.now(timezone.utc),
        database=DatabaseHealth(
            status="connected" if is_connected else "disconnected",
            target=active_settings.safe_database_target(),
            latency_ms=latency_ms,
            message=message,
        ),
    )
