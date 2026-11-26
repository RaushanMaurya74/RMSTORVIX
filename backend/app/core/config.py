"""Application settings loaded from environment variables and optional .env file."""

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_UNSUPPORTED_PSYCOPG_QUERY_KEYS = {"pgbouncer", "connection_limit", "schema"}


def _normalize_sqlalchemy_postgres_url(raw_url: str) -> str:
    """Normalize postgres:// or postgresql:// URLs to psycopg3 and strip non-libpq params."""
    cleaned = raw_url.strip().strip('"').strip("'").strip()
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgres://") :]
    elif cleaned.startswith("postgresql://"):
        cleaned = "postgresql+psycopg://" + cleaned[len("postgresql://") :]

    scheme, sep, rest = cleaned.partition("://")
    if sep and "@" in rest:
        userinfo, _, host_path_query = rest.rpartition("@")
        if any(ch in userinfo for ch in ("@", "#", "?", "/", "[", "]")):
            username, psep, password = userinfo.partition(":")
            host_and_path, qsep, raw_query = host_path_query.partition("?")
            host_port, _, db_path = host_and_path.partition("/")
            if ":" in host_port and not host_port.startswith("["):
                host_only, _, port_str = host_port.rpartition(":")
                port_val = int(port_str) if port_str.isdigit() else None
            else:
                host_only = host_port
                port_val = None
            kept_query = (
                {
                    k: v
                    for k, v in parse_qsl(raw_query, keep_blank_values=True)
                    if k.lower() not in _UNSUPPORTED_PSYCOPG_QUERY_KEYS
                }
                if qsep
                else {}
            )
            return URL.create(
                drivername=scheme,
                username=unquote(username),
                password=password if psep else None,
                host=host_only,
                port=port_val,
                database=db_path or None,
                query=kept_query,
            ).render_as_string(hide_password=False)

    if "?" in cleaned:
        parts = urlsplit(cleaned)
        kept_params = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _UNSUPPORTED_PSYCOPG_QUERY_KEYS
        ]
        cleaned = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(kept_params), parts.fragment)
        )
    return cleaned


class Settings(BaseSettings):
    """Typed runtime settings for FastAPI, Vercel serverless, and Supabase PostgreSQL/Storage."""

    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("VERCEL") else PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Invoice & Billing System")
    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development"
    )
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)

    # Frontend / CORS / API routing configuration (zero secrets exposed)
    frontend_url: str = Field(default="")
    api_base_url: str = Field(default="")
    cors_origins: str = Field(
        default="http://127.0.0.1:8000,http://localhost:8000",
        description="Comma-separated list of allowed CORS origins.",
    )
    allowed_origins: str = Field(
        default="",
        description="Optional comma-separated alias merged with CORS_ORIGINS for deployment.",
    )

    # PostgreSQL / Supabase connection settings
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="invoice_billing")
    postgres_user: str = Field(default="invoice_app")
    postgres_password: SecretStr = Field(default=SecretStr(""))

    # Primary connection URL (recommended for Supabase Session/Transaction Pooler)
    database_url: SecretStr | None = Field(default=None)

    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_connect_timeout_seconds: int = Field(default=8, ge=1, le=60)
    db_use_nullpool: bool | None = Field(default=None)
    db_ssl_require: bool | None = Field(default=None)
    db_disable_prepared_statements: bool | None = Field(default=None)

    # Storage backend ("auto" switches to Supabase when SUPABASE_URL + service role key are set)
    storage_backend: Literal["auto", "local", "supabase"] = Field(default="auto")
    storage_pdf_dir: str = Field(default="storage/pdfs")
    storage_signature_dir: str = Field(default="storage/signatures")
    signature_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    storage_logo_dir: str = Field(default="storage/logos")
    logo_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)

    # Supabase Storage persistent bucket configuration (never exposed to browser)
    supabase_url: str = Field(default="")
    supabase_service_role_key: SecretStr = Field(default=SecretStr(""))
    supabase_storage_bucket: str = Field(default="rmstorvix-private")
    supabase_storage_signed_url_ttl: int = Field(default=300, ge=30, le=86400)

    # Optional external GSTIN verification provider (also supports GST_VERIFICATION_API_KEY env alias)
    gstin_api_url: str = Field(default="")
    gstin_api_key: SecretStr = Field(default=SecretStr(""))
    gst_verification_api_key: SecretStr = Field(default=SecretStr(""))
    gstin_api_timeout_seconds: int = Field(default=6, ge=1, le=30)

    # Optional signing key / mail configuration placeholders for production extensions
    jwt_secret_key: SecretStr = Field(default=SecretStr(""))
    mail_configuration: str = Field(default="")

    # Session & cookie settings
    session_cookie_name: str = Field(default="inv_session")
    session_ttl_hours: int = Field(default=24, ge=1, le=720)
    cookie_secure: bool = Field(default=False)
    cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax")

    # Separate Admin Panel session & initial seeding settings (never exposed to frontend)
    admin_session_cookie_name: str = Field(default="rmx_admin_session")
    admin_session_ttl_hours: int = Field(default=12, ge=1, le=168)
    initial_admin_email: str = Field(default="")
    initial_admin_password: SecretStr = Field(default=SecretStr(""))
    initial_admin_name: str = Field(default="RMSTORVIX Administrator")

    # SaaS policy defaults & activation rate limits
    support_email: str = Field(default="support@rmstorvix.com")
    support_phone: str = Field(default="+91-1800-000-0000")
    enforce_subscription_expiry: bool = Field(default=True)
    allow_self_activation: bool = Field(default=True)
    notification_intervals_days: str = Field(default="30,15,7,3,1,0")
    activation_rate_limit_max_attempts: int = Field(default=8, ge=3, le=50)
    activation_rate_limit_window_minutes: int = Field(default=15, ge=1, le=120)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_serverless(self) -> bool:
        """Detect serverless runtimes such as Vercel Python Functions where project root is read-only."""
        return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_cookie_secure(self) -> bool:
        """Require Secure cookies on HTTPS/production/Vercel while keeping HTTP localhost functional in dev."""
        return bool(self.cookie_secure or self.app_env == "production" or self.is_serverless)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_gstin_api_key(self) -> str:
        """Return configured GST verification key supporting both GSTIN_API_KEY and GST_VERIFICATION_API_KEY."""
        primary = self.gstin_api_key.get_secret_value().strip()
        if primary:
            return primary
        return self.gst_verification_api_key.get_secret_value().strip()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_storage_backend(self) -> Literal["local", "supabase"]:
        """Use Supabase Storage in cloud deployments when credentials are configured, or local disk otherwise."""
        if self.storage_backend == "local":
            return "local"
        has_supabase = bool(
            self.supabase_url.strip() and self.supabase_service_role_key.get_secret_value().strip()
        )
        if self.storage_backend == "supabase" or has_supabase:
            return "supabase"
        return "local"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse and deduplicate authorized CORS origins from env variables and deployment hosts."""
        candidates: list[str] = []
        for raw_group in (self.cors_origins, self.allowed_origins):
            for origin in raw_group.split(","):
                cleaned = origin.strip().rstrip("/")
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)
        if self.frontend_url.strip():
            fe = self.frontend_url.strip().rstrip("/")
            if fe not in candidates:
                candidates.append(fe)
        for env_key in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
            host_val = os.environ.get(env_key, "").strip().rstrip("/")
            if host_val:
                origin = host_val if host_val.startswith("http") else f"https://{host_val}"
                if origin not in candidates:
                    candidates.append(origin)
        return candidates

    def _resolve_storage_path(self, configured: str) -> Path:
        path = Path(configured)
        if path.is_absolute():
            return path
        # Vercel serverless deployments mount the codebase read-only at /var/task; /tmp is writable.
        if self.is_serverless:
            return Path("/tmp") / "rmstorvix" / path
        return PROJECT_ROOT / path

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_pdf_dir(self) -> Path:
        """Resolve the managed PDF storage directory."""
        return self._resolve_storage_path(self.storage_pdf_dir)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_signature_dir(self) -> Path:
        """Resolve the managed signature storage directory."""
        return self._resolve_storage_path(self.storage_signature_dir)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_logo_dir(self) -> Path:
        """Resolve the managed business logo storage directory."""
        return self._resolve_storage_path(self.storage_logo_dir)

    def resolved_database_url_entry(self) -> tuple[str, str]:
        """Return `(source_env_name, raw_url)` checking DATABASE_URL and standard hosting aliases."""
        if self.database_url is not None:
            raw_url = self.database_url.get_secret_value().strip()
            if raw_url:
                return ("DATABASE_URL", raw_url)

        for alias in (
            "POSTGRES_URL",
            "POSTGRES_PRISMA_URL",
            "POSTGRES_URL_NON_POOLING",
            "SUPABASE_DB_URL",
            "SUPABASE_DATABASE_URL",
        ):
            alias_val = os.environ.get(alias, "").strip()
            if alias_val:
                return (alias, alias_val)

        return ("", "")

    def database_url_diagnostics(self) -> dict[str, object]:
        """Return non-secret presence and length telemetry for runtime database env diagnostics."""
        env_raw = os.environ.get("DATABASE_URL")
        pydantic_raw = self.database_url.get_secret_value() if self.database_url is not None else None
        source, resolved = self.resolved_database_url_entry()
        present_aliases = [
            alias
            for alias in (
                "POSTGRES_URL",
                "POSTGRES_PRISMA_URL",
                "POSTGRES_URL_NON_POOLING",
                "SUPABASE_DB_URL",
                "SUPABASE_DATABASE_URL",
            )
            if alias in os.environ
        ]
        return {
            "database_url_env_present": env_raw is not None,
            "database_url_env_length": len(env_raw.strip()) if env_raw is not None else 0,
            "settings_database_url_present": pydantic_raw is not None,
            "settings_database_url_length": len(pydantic_raw.strip()) if pydantic_raw is not None else 0,
            "resolved_source": source or None,
            "resolved_non_empty": bool(resolved),
            "present_aliases": present_aliases,
        }

    def build_sqlalchemy_url(self) -> URL | str:
        """Return the SQLAlchemy connection URL without storing plaintext secrets in logs."""
        _, raw_url = self.resolved_database_url_entry()
        if raw_url:
            return _normalize_sqlalchemy_postgres_url(raw_url)

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    def safe_database_target(self) -> str:
        """Return a sanitized host/port/database label with credentials removed."""
        raw_or_url = self.build_sqlalchemy_url()
        try:
            parsed = make_url(raw_or_url)
        except Exception:
            return "postgresql+psycopg://invalid_url_format"
        driver = parsed.drivername
        if parsed.host or parsed.database:
            host = (parsed.host or "localhost").rsplit("@", 1)[-1]
            port_part = f":{parsed.port}" if parsed.port else ""
            db_part = f"/{parsed.database}" if parsed.database else ""
            return f"{driver}://{host}{port_part}{db_part}"
        return f"{driver}://configured"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
