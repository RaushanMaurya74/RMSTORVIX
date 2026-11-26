"""Tests for health-check service, routes, and frontend shell serving."""

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine

from app.core.config import Settings
from app.main import create_app
from app.services.health_service import get_system_health


def test_health_service_reports_ok_when_database_reachable() -> None:
    """Health service should report ok when SELECT 1 succeeds."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    settings = Settings(
        app_env="test",
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
    )

    try:
        health = get_system_health(settings=settings, engine=engine)
    finally:
        engine.dispose()

    assert health.status == "ok"
    assert health.environment == "test"
    assert health.database.status == "connected"
    assert health.database.latency_ms is not None
    assert health.database.latency_ms >= 0


def test_health_service_reports_degraded_without_leaking_secrets() -> None:
    """Health service should degrade gracefully and never expose database credentials."""
    failing_engine = create_engine(
        "postgresql+psycopg://secret_user:secret_pass@127.0.0.1:1/unreachable_db",
        connect_args={"connect_timeout": 1},
    )
    settings = Settings(
        app_env="test",
        postgres_host="127.0.0.1",
        postgres_port=1,
        postgres_db="unreachable_db",
        postgres_user="secret_user",
        postgres_password=SecretStr("secret_pass"),
    )

    try:
        health = get_system_health(settings=settings, engine=failing_engine)
    finally:
        failing_engine.dispose()

    assert health.status == "degraded"
    assert health.database.status == "disconnected"
    assert health.database.latency_ms is None
    assert "secret_pass" not in health.database.message
    assert "secret_pass" not in health.database.target
    assert "secret_user" not in health.database.target


def test_health_endpoints_return_200_when_healthy(monkeypatch) -> None:
    """Both /health and /api/v1/health should return 200 OK when service health is ok."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    test_settings = Settings(app_env="test")

    def fake_get_system_health():
        return get_system_health(settings=test_settings, engine=engine)

    monkeypatch.setattr("app.api.health.get_system_health", fake_get_system_health)

    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        root_resp = client.get("/health")
        v1_resp = client.get("/api/v1/health")
        index_resp = client.get("/")

    engine.dispose()

    assert root_resp.status_code == 200
    assert v1_resp.status_code == 200
    assert root_resp.json()["status"] == "ok"
    assert v1_resp.json()["database"]["status"] == "connected"
    assert index_resp.status_code == 200
    assert "text/html" in index_resp.headers["content-type"]


def test_health_endpoints_return_503_when_database_unavailable(monkeypatch) -> None:
    """Both /health and /api/v1/health should return 503 when database is disconnected."""
    test_settings = Settings(
        app_env="test",
        postgres_host="127.0.0.1",
        postgres_port=1,
        postgres_db="missing_db",
        postgres_user="app_user",
        postgres_password=SecretStr("hidden_pw"),
    )
    failing_engine = create_engine(
        "postgresql+psycopg://app_user:hidden_pw@127.0.0.1:1/missing_db",
        connect_args={"connect_timeout": 1},
    )

    def fake_get_system_health():
        return get_system_health(settings=test_settings, engine=failing_engine)

    monkeypatch.setattr("app.api.health.get_system_health", fake_get_system_health)

    app = create_app(settings=test_settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    failing_engine.dispose()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "disconnected"
    assert "hidden_pw" not in str(body)


def test_spa_navigation_routes_serve_index_html() -> None:
    """All sidebar module routes serve index.html so browser refreshes never 404."""
    app = create_app(settings=Settings(app_env="test"))
    with TestClient(app) as client:
        for path in (
            "/dashboard",
            "/invoices",
            "/invoices/new",
            "/invoices/42",
            "/customers",
            "/products",
            "/inventory",
            "/payments",
            "/reports",
            "/notifications",
            "/settings",
        ):
            resp = client.get(path)
            assert resp.status_code == 200, f"Failed on {path}"
            assert "text/html" in resp.headers["content-type"]
