#!/usr/bin/env python
"""Script to create database tables (including pgvector extension)."""

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
from app.core.constants import (
    DEFAULT_TENANT_ID,
    DEFAULT_TENANT_NAME,
    DEFAULT_TENANT_SLUG,
)
from app.db.base import Base

# Import ALL models so their tables are registered with Base.metadata
from app.models import (  # noqa: F401
    Tenant,
    User,
    Conversation,
    ConversationState,
    Document,
    Chunk,
    QueryLog,
)

settings = get_settings()


def create_tables(drop_existing: bool = False):
    """Create all database tables."""
    engine = create_engine(settings.database_url_sync, echo=True)

    # Enable pgvector extension first
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    print("✓ pgvector extension enabled")

    if drop_existing:
        print("Dropping existing tables...")
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS query_logs CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS chunks CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS documents CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS conversation_states CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS conversations CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS tenants CASCADE"))
            conn.commit()
        print("✓ Existing tables dropped")

    Base.metadata.create_all(engine)
    print("✓ All tables created successfully")

    # Create default tenant
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO tenants (id, name, slug, is_active, created_at, updated_at)
                VALUES (
                    :tenant_id::uuid,
                    :name,
                    :slug,
                    :is_active,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (slug) DO NOTHING
                """),
            {
                "tenant_id": str(DEFAULT_TENANT_ID),
                "name": DEFAULT_TENANT_NAME,
                "slug": DEFAULT_TENANT_SLUG,
                "is_active": True,
            },
        )
        conn.commit()
    print("✓ Default tenant created")

    # Print created tables
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        tables = [row[0] for row in result]
        print(f"\nTables in database: {', '.join(tables)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create ClarityQL database tables")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating",
    )
    args = parser.parse_args()

    create_tables(drop_existing=args.drop)
