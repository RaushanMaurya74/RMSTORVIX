"""SQLAlchemy 2.x database engine, serverless pooling, and session dependency."""

from collections.abc import Generator
import time
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


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
        is_supabase_host = "supabase.co" in host_lower or "supabase.com" in host_lower
        is_pooler_endpoint = "pooler.supabase.com" in host_lower or parsed.port == 6543

        # Enforce TLS when connecting to Supabase or explicitly configured, unless URL specifies sslmode
        ssl_required = (
            active_settings.db_ssl_require
            if active_settings.db_ssl_require is not None
            else (is_supabase_host or active_settings.app_env == "production")
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


def check_database_connection(engine: Engine | None = None) -> tuple[bool, float | None, str]:
    """Execute a lightweight SELECT 1 check without exposing credentials or stack traces."""
    target_engine = engine or get_engine()
    started = time.perf_counter()
    try:
        with target_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return True, latency_ms, "Database connection verified."
    except SQLAlchemyError:
        return False, None, "Database connection failed."
    except Exception:
        return False, None, "Database connectivity check encountered an unexpected error."
