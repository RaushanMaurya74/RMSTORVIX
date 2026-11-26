"""Shared pytest fixtures providing isolated database sessions and TestClient."""

from collections.abc import Generator
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
import app.models  # noqa: F401
from app.models import Base


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Create an isolated SQLite database per test."""
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to the isolated test database session."""
    app = create_app(settings=Settings(app_env="test"))

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client._db_session = db_session  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
