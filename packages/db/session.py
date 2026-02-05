"""Session management for database access."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from packages.db.base import get_engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
