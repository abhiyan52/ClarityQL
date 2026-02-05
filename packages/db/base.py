"""SQLAlchemy base and engine configuration."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase


def get_database_url() -> str:
    """Return database URL from environment or default local Postgres."""

    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/clarityql",
    )


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_engine():
    """Create a SQLAlchemy engine for the configured database."""

    return create_engine(get_database_url())
