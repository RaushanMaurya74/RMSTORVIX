"""Tests for environment-driven application and PostgreSQL configuration."""

from pydantic import SecretStr

from app.core.config import Settings


def test_settings_build_postgres_url_from_env_fields() -> None:
    """PostgreSQL URL should assemble from POSTGRES_* settings with psycopg driver."""
    settings = Settings(
        postgres_host="db.internal",
        postgres_port=5433,
        postgres_db="billing_db",
        postgres_user="billing_user",
        postgres_password=SecretStr("super-secret-password"),
        database_url=None,
    )

    url = settings.build_sqlalchemy_url()
    url_text = str(url)

    assert "postgresql+psycopg://" in url_text
    assert "db.internal:5433/billing_db" in url_text
    assert settings.safe_database_target() == "postgresql+psycopg://db.internal:5433/billing_db"
    assert "super-secret-password" not in settings.safe_database_target()
    assert "billing_user" not in settings.safe_database_target()


def test_settings_database_url_override_never_leaks_credentials() -> None:
    """Explicit DATABASE_URL override should still produce a credential-free target label."""
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://admin:top_secret@pg.example:5432/prod_inv")
    )

    target = settings.safe_database_target()

    assert target == "postgresql+psycopg://pg.example:5432/prod_inv"
    assert "top_secret" not in target
    assert "admin" not in target


def test_cors_origin_list_parses_comma_separated_values() -> None:
    """CORS origins string should split cleanly into trimmed origin URLs."""
    settings = Settings(cors_origins="http://localhost:8000, https://app.example.com ")

    assert settings.cors_origin_list == [
        "http://localhost:8000",
        "https://app.example.com",
    ]
