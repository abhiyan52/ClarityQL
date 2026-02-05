#!/usr/bin/env python
"""Script to create database tables."""

import sys
from pathlib import Path

# Add project root and backend app to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "apps" / "backend"))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.base import Base
from app.models import User, Conversation, ConversationState  # noqa: F401

settings = get_settings()


def create_tables(drop_existing: bool = False):
    """Create all database tables."""
    engine = create_engine(settings.database_url_sync, echo=True)

    if drop_existing:
        print("Dropping existing tables...")
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS conversation_states CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS conversations CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            conn.commit()
        print("✓ Existing tables dropped")

    Base.metadata.create_all(engine)
    print("✓ All tables created successfully")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating",
    )
    args = parser.parse_args()

    create_tables(drop_existing=args.drop)
