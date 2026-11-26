"""SQLAlchemy 2.x database engine, serverless pooling, and session dependency."""

from collections.abc import Generator
import logging
import re
import time
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.db.session")
_CREDENTIAL_URI_RE = re.compile(r"([a-zA-Z0-9+_-]+://)([^:@/\s]+):([^@/\s]+)@")


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def redact_connection_secrets(raw_text: str) -> str:
    """Strip any embedded credentials from exception strings before logging."""
    return _CREDENTIAL_URI_RE.sub(r"\1***:***@", raw_text or "")


def classify_db_error(exc: Exception, *, settings: Settings | None = None) -> str:
    """Translate low-level driver exceptions into safe, actionable diagnostic messages."""
    active_settings = settings or get_settings()
    raw_msg = redact_connection_secrets(str(exc)).lower()

    diag = active_settings.database_url_diagnostics()
    has_non_local_pg_host = active_settings.postgres_host not in {"", "localhost", "127.0.0.1", "::1"}
    if active_settings.is_serverless and not diag["resolved_non_empty"] and not has_non_local_pg_host:
        if diag["database_url_env_present"] and diag["database_url_env_length"] == 0:
            return (
                "DATABASE_URL is present in the serverless runtime environment but its value is empty (length=0). "
                "Update DATABASE_URL in Vercel Environment Variables with your Supabase Transaction Pooler URI (:6543) and redeploy."
            )
        return (
            "DATABASE_URL environment variable is not set in the serverless runtime. "
            "Add Supabase Transaction Pooler URI (:6543) to environment variables and redeploy."
        )
    if "password authentication failed" in raw_msg or "authentication failed" in raw_msg:
        return "PostgreSQL authentication failed. Verify the username and password in DATABASE_URL."
    if "ssl" in raw_msg and ("error" in raw_msg or "required" in raw_msg or "certificate" in raw_msg):
        return "PostgreSQL SSL connection failed. Ensure sslmode=require is enabled for Supabase."
    if (
        "could not translate host" in raw_msg
        or "name or service not known" in raw_msg
        or "getaddrinfo" in raw_msg
        or "network is unreachable" in raw_msg
        or "cannot assign requested address" in raw_msg
    ):
        return (
            "Database host unreachable. On Vercel serverless, use Supabase Transaction Pooler "
            "(host ending in .pooler.supabase.com on port 6543)."
        )
    if "timeout" in raw_msg or "timed out" in raw_msg:
        return "Database connection timed out. Check Supabase Pooler port 6543 and network reachability."
    if "connection refused" in raw_msg:
        return "Database connection refused at the configured host/port."
    if "database" in raw_msg and "does not exist" in raw_msg:
        return "Target PostgreSQL database name in DATABASE_URL does not exist."
    return "Database connection failed. Check DATABASE_URL configuration."


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Create a configured SQLAlchemy engine tuned for Supabase PostgreSQL & serverless runtimes."""
    active_settings = settings or get_settings()
    url = active_settings.build_sqlalchemy_url()
    parsed = make_url(url)
    url_str = str(url)

    engine_kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "future": True,
    }

    if url_str.startswith("postgresql"):
        connect_args: dict[str, Any] = {
            "connect_timeout": active_settings.db_connect_timeout_seconds,
        }
        host_lower = (parsed.host or "").lower()
        is_local_host = host_lower in {"localhost", "127.0.0.1", "::1"}
        is_supabase_host = "supabase.co" in host_lower or "supabase.com" in host_lower
        is_pooler_endpoint = "pooler.supabase.com" in host_lower or parsed.port == 6543

        # Enforce TLS for Supabase or remote production hosts unless URL specifies sslmode
        ssl_required = (
            active_settings.db_ssl_require
            if active_settings.db_ssl_require is not None
            else (is_supabase_host or (active_settings.app_env == "production" and not is_local_host))
        )
        if ssl_required and "sslmode" not in parsed.query:
            connect_args["sslmode"] = "require"

        # Supabase Transaction Pooler (Supavisor :6543) does not support server-side prepared statements
        disable_prepared = (
            active_settings.db_disable_prepared_statements
            if active_settings.db_disable_prepared_statements is not None
            else is_pooler_endpoint
        )
        if disable_prepared:
            connect_args["prepare_threshold"] = None

        # Serverless deployments (Vercel) and external connection poolers should use NullPool
        use_nullpool = (
            active_settings.db_use_nullpool
            if active_settings.db_use_nullpool is not None
            else (active_settings.is_serverless or is_pooler_endpoint)
        )
        if use_nullpool:
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs["pool_size"] = active_settings.db_pool_size
            engine_kwargs["max_overflow"] = active_settings.db_max_overflow

        engine_kwargs["connect_args"] = connect_args

    return create_engine(url, **engine_kwargs)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the lazily initialized singleton SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the lazily initialized SQLAlchemy session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


def reset_db_engine() -> None:
    """Dispose and reset cached engine/session factory (used in tests and reconfiguration)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database_connection(
    engine: Engine | None = None,
    settings: Settings | None = None,
) -> tuple[bool, float | None, str]:
    """Execute a lightweight SELECT 1 check, logging sanitized diagnostics without secrets."""
    active_settings = settings or get_settings()
    started = time.perf_counter()
    try:
        target_engine = engine or get_engine()
        with target_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return True, latency_ms, "Database connection verified."
    except SQLAlchemyError as exc:
        logger.error(
            "Database health check failed (%s) target=%s diag=%s: %s",
            type(exc).__name__,
            active_settings.safe_database_target(),
            active_settings.database_url_diagnostics(),
            redact_connection_secrets(str(exc)),
        )
        return False, None, classify_db_error(exc, settings=active_settings)
    except Exception as exc:
        logger.error(
            "Database configuration/connectivity error (%s) target=%s diag=%s: %s",
            type(exc).__name__,
            active_settings.safe_database_target(),
            active_settings.database_url_diagnostics(),
            redact_connection_secrets(str(exc)),
        )
        return False, None, classify_db_error(exc, settings=active_settings)
