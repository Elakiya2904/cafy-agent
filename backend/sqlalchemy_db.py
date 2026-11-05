"""SQLAlchemy 2.x database configuration for the PostgreSQL migration.

The legacy database adapter remains separate until the application services are
migrated to SQLAlchemy and the Alembic schema has been validated.
"""
from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def database_url() -> str:
    """Return the configured SQLAlchemy PostgreSQL URL."""
    value = (os.getenv("DATABASE_URL") or "").strip()
    if not value:
        raise RuntimeError(
            "DATABASE_URL is required for the SQLAlchemy database. "
            "Use postgresql+psycopg://postgres:<password>@localhost:5432/cafy_agent."
        )
    if not value.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("DATABASE_URL must use PostgreSQL with the psycopg driver.")
    return value if "+psycopg" in value else value.replace("postgresql://", "postgresql+psycopg://", 1)


def build_engine(url: str | None = None) -> Engine:
    """Build a pooled SQLAlchemy engine from an explicit or environment URL."""
    configured_url = url or database_url()
    if not configured_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("SQLAlchemy database URL must use PostgreSQL with the psycopg driver.")
    return create_engine(
        configured_url if "+psycopg" in configured_url else configured_url.replace("postgresql://", "postgresql+psycopg://", 1),
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_POOL_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    )


engine = build_engine() if os.getenv("DATABASE_URL", "").strip() else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False) if engine else None


def session_scope() -> Generator[Session, None, None]:
    """Yield a transaction-scoped session and roll back failed work."""
    if SessionLocal is None:
        raise RuntimeError("SQLAlchemy database is not configured; set DATABASE_URL first.")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def connection_check() -> Generator[dict[str, Any], None, None]:
    """Check PostgreSQL connectivity and return the server version."""
    if engine is None:
        raise RuntimeError("SQLAlchemy database is not configured; set DATABASE_URL first.")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar_one()
        yield {"database_url": engine.url.render_as_string(hide_password=True), "version": version}
