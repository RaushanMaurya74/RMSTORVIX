"""Deployment readiness tests for Vercel entrypoint, Supabase pooling, storage adapter, and public config."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import create_db_engine
from app.services.storage_service import (
    create_signed_storage_url,
    delete_stored_object,
    get_stored_bytes,
    put_stored_bytes,
)
from tests.helpers import activate_registered_account


def test_vercel_api_entrypoint_exports_fastapi_app() -> None:
    """Root api/index.py should expose the working FastAPI ASGI app for Vercel Python Runtime."""
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from api.index import app as vercel_app  # type: ignore[import-not-found]

    route_paths = {getattr(route, "path", None) for route in vercel_app.routes}
    api_paths = set(vercel_app.openapi()["paths"].keys())
    assert "/health" in api_paths
    assert "/api/v1/health" in api_paths
    assert "/api/v1/auth/login" in api_paths
    assert "/api/v1/admin/overview" in api_paths
    assert "/app-config.js" in route_paths
    assert "/" in route_paths
    assert "/admin" in route_paths


def test_app_config_js_is_public_and_secret_free(client: TestClient) -> None:
    """/app-config.js exposes only non-secret runtime values for frontend API routing."""
    resp = client.get("/app-config.js")
    assert resp.status_code == 200
    assert "application/javascript" in resp.headers.get("content-type", "")
    body = resp.text
    assert "__RMSTORVIX_CONFIG__" in body
    assert '"apiBaseUrl"' in body
    for forbidden in [
        "database_url",
        "supabase_service_role_key",
        "jwt_secret_key",
        "initial_admin_password",
        "postgres_password",
    ]:
        assert forbidden not in body.lower()


def test_supabase_url_normalization_and_serverless_settings(monkeypatch) -> None:
    """Settings normalize Supabase URLs, merge origins, enforce HTTPS cookies in prod, and isolate serverless storage."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_URL", "rmstorvix-preview.vercel.app")
    cfg = Settings(
        app_env="production",
        database_url="postgres://postgres.abc:secret@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
        frontend_url="https://billing.rmstorvix.com/",
        allowed_origins="https://admin.rmstorvix.com",
        supabase_url="https://abc.supabase.co",
        supabase_service_role_key="service-role-secret-test",
    )

    assert str(cfg.build_sqlalchemy_url()).startswith("postgresql+psycopg://")
    assert "service-role-secret-test" not in cfg.safe_database_target()
    assert cfg.is_serverless is True
    assert cfg.effective_cookie_secure is True
    assert cfg.effective_storage_backend == "supabase"
    assert str(cfg.resolved_pdf_dir).replace("\\", "/").startswith("/tmp/rmstorvix/")
    assert "https://billing.rmstorvix.com" in cfg.cors_origin_list
    assert "https://admin.rmstorvix.com" in cfg.cors_origin_list
    assert "https://rmstorvix-preview.vercel.app" in cfg.cors_origin_list

    # Verify Supabase pooler engine builds with NullPool and pooler-safe args
    engine = create_db_engine(cfg)
    assert engine.pool.__class__.__name__ == "NullPool"
    engine.dispose()


def test_supabase_storage_adapter_roundtrip_and_signed_url_endpoints(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Supabase storage helper sends authorized requests and authenticated signed-url routes protect tenant isolation."""
    cfg = Settings(
        storage_backend="supabase",
        supabase_url="https://demo.supabase.co",
        supabase_service_role_key="sb-secret-key",
        supabase_storage_bucket="rmstorvix-private",
    )

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = MagicMock(
        status_code=200, json=lambda: {"signedURL": "/object/sign/rmstorvix-private/logos/biz_1/logo.png?token=abc"}
    )
    mock_client.get.return_value = MagicMock(status_code=200, content=b"PNGDATA")
    mock_client.delete.return_value = MagicMock(status_code=200)

    with patch("app.services.storage_service.httpx.Client", return_value=mock_client):
        put_stored_bytes(
            namespace="logos",
            base_dir=tmp_path,
            storage_key="biz_1/logo.png",
            data=b"PNGDATA",
            content_type="image/png",
            settings=cfg,
        )
        assert (
            get_stored_bytes(
                namespace="logos",
                base_dir=tmp_path,
                storage_key="biz_1/logo.png",
                settings=cfg,
            )
            == b"PNGDATA"
        )
        signed = create_signed_storage_url(
            namespace="logos",
            storage_key="biz_1/logo.png",
            settings=cfg,
        )
        assert signed == "https://demo.supabase.co/storage/v1/object/sign/rmstorvix-private/logos/biz_1/logo.png?token=abc"
        delete_stored_object(
            namespace="logos",
            base_dir=tmp_path,
            storage_key="biz_1/logo.png",
            settings=cfg,
        )

    # Signed URL endpoints must reject unauthenticated calls and work for authenticated users
    assert client.get("/api/v1/business/logo/signed-url").status_code == 401
    assert client.get("/api/v1/business/signature/signed-url").status_code == 401

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Deploy Owner",
            "email": "deploy@ready.test",
            "password": "Password123!",
            "business_name": "Ready Corp",
        },
    )
    assert reg.status_code == 201
    activate_registered_account(client, "deploy@ready.test")
    logo_signed = client.get("/api/v1/business/logo/signed-url")
    assert logo_signed.status_code == 200
    assert logo_signed.json()["url"] == "/api/v1/business/logo"


def test_support_endpoint_falls_back_gracefully_when_db_unavailable(client: TestClient) -> None:
    """/api/v1/saas/support should return configured support contact instead of 500 if DB is unreachable."""
    from sqlalchemy.exc import OperationalError

    with patch(
        "app.services.saas_service.get_saas_settings",
        side_effect=OperationalError("SELECT 1", {}, Exception("conn refused")),
    ):
        resp = client.get("/api/v1/saas/support")
    assert resp.status_code == 200
    data = resp.json()
    assert "support_email" in data
    assert "support_phone" in data


def test_database_url_normalization_and_secret_redaction() -> None:
    """Strips quotes and unsupported query params, and redacts credentials from diagnostic logs."""
    from app.db.session import classify_db_error, redact_connection_secrets

    cfg = Settings(
        database_url='"postgres://postgres.xyz:SuperSecret@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true&sslmode=require"',
    )
    url = str(cfg.build_sqlalchemy_url())
    assert url.startswith("postgresql+psycopg://")
    assert "pgbouncer" not in url
    assert "sslmode=require" in url
    assert "SuperSecret" not in cfg.safe_database_target()

    leaked = "psycopg error on postgresql+psycopg://postgres.xyz:SuperSecret@host:6543/postgres"
    redacted = redact_connection_secrets(leaked)
    assert "SuperSecret" not in redacted
    assert "***:***" in redacted

    msg = classify_db_error(Exception("password authentication failed for user postgres"), settings=cfg)
    assert "authentication failed" in msg.lower()


def test_postgres_url_alias_fallback_and_non_secret_diagnostics(monkeypatch) -> None:
    """Supports POSTGRES_URL/SUPABASE_DB_URL fallbacks and reports non-empty diagnostics without secrets."""
    from app.db.session import classify_db_error

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_URL", "postgres://postgres.abc:AliasSecret@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres")

    cfg = Settings(database_url=None)
    assert str(cfg.build_sqlalchemy_url()).startswith("postgresql+psycopg://")
    diag = cfg.database_url_diagnostics()
    assert diag["database_url_env_present"] is True
    assert diag["database_url_env_length"] == 0
    assert diag["resolved_source"] == "POSTGRES_URL"
    assert diag["resolved_non_empty"] is True
    assert "AliasSecret" not in str(diag)
    assert "AliasSecret" not in cfg.safe_database_target()

    monkeypatch.delenv("POSTGRES_URL")
    empty_cfg = Settings(database_url=None)
    empty_msg = classify_db_error(Exception("connection refused"), settings=empty_cfg)
    assert "length=0" in empty_msg


def test_database_url_unescaped_special_chars_and_discrete_pg_fields(monkeypatch) -> None:
    """Safely encodes unescaped @/# in DATABASE_URL passwords without leaking fragments, and supports POSTGRES_* fields."""
    from sqlalchemy.engine import make_url
    from app.db.session import classify_db_error

    raw = "postgresql://postgres.ondxlqfdotzlerpfqjxc:p@ss#word@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true&sslmode=require"
    cfg = Settings(database_url=raw)
    built = make_url(cfg.build_sqlalchemy_url())
    assert built.username == "postgres.ondxlqfdotzlerpfqjxc"
    assert built.password == "p@ss#word"
    assert built.host == "aws-0-ap-northeast-1.pooler.supabase.com"
    assert built.port == 6543
    assert built.database == "postgres"
    assert "pgbouncer" not in dict(built.query)
    assert dict(built.query).get("sslmode") == "require"
    assert "p@ss" not in cfg.safe_database_target()
    assert "#word" not in cfg.safe_database_target()

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    pg_cfg = Settings(
        database_url=None,
        postgres_host="aws-0-ap-northeast-1.pooler.supabase.com",
        postgres_port=6543,
        postgres_db="postgres",
        postgres_user="postgres.ondxlqfdotzlerpfqjxc",
        postgres_password="raw@password#1",
    )
    pg_url = pg_cfg.build_sqlalchemy_url()
    assert pg_url.host == "aws-0-ap-northeast-1.pooler.supabase.com"
    auth_msg = classify_db_error(Exception("password authentication failed for user postgres"), settings=pg_cfg)
    assert "authentication failed" in auth_msg.lower()




