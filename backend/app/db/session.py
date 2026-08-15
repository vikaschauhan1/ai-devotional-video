"""Database engine and session factory.

Sync SQLAlchemy 2.0 style. SQLite for MVP; a PostgreSQL DSN in
``DATABASE_URL`` works without any code changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import get_settings
from backend.app.db.base import Base


def _make_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # Allow FastAPI's threadpool to reuse the connection safely.
        connect_args["check_same_thread"] = False
        # Ensure the parent directory exists for file-backed sqlite URLs
        # like ``sqlite:///./data/app.db``.
        if "///" in url:
            db_path = Path(url.split("///", 1)[1])
            if not db_path.is_absolute():
                db_path = settings.repo_root / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True, connect_args=connect_args)


engine: Engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create tables. Alembic replaces this later."""
    # Import so models register on the metadata before create_all runs.
    from backend.app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
