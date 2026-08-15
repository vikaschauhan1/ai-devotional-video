"""Test fixtures: isolated SQLite per-session, TestClient with DB override."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Point the app at a temp SQLite file BEFORE the app imports settings.
_TMP_DB = Path(tempfile.gettempdir()) / f"ai-dev-video-test-{os.getpid()}.sqlite"
_TMP_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["APP_ENV"] = "test"

from backend.app.core.settings import get_settings  # noqa: E402
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.session import get_db as real_get_db  # noqa: E402
from backend.app.main import app  # noqa: E402

get_settings.cache_clear()  # ensure test env vars are picked up


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        f"sqlite:///{_TMP_DB}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    # Import models so metadata is populated, then create schema.
    from backend.app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    _TMP_DB.unlink(missing_ok=True)


@pytest.fixture()
def db_session(test_engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(test_engine) -> Iterator[TestClient]:
    session_factory = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

    def override() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[real_get_db] = override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(real_get_db, None)
