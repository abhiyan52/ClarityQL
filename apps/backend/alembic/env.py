"""Alembic environment configuration.

Reads the database URL from app settings (which reads from .env)
and imports all SQLAlchemy models so autogenerate can detect changes.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the backend app package is importable
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # alembic/ -> backend/
_PROJECT_ROOT = _BACKEND_DIR.parent.parent  # backend -> apps -> project root

sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env before importing app settings
from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Import app settings & models (triggers table registration on Base.metadata)
# ---------------------------------------------------------------------------
from app.core.config import get_settings
from app.db.base import Base

# Import ALL models so their tables are registered with Base.metadata.
# This is critical for autogenerate to detect them.
from app.models import (  # noqa: F401
    Tenant,
    User,
    Conversation,
    ConversationState,
    Document,
    Chunk,
    QueryLog,
    Task,
)

# ---------------------------------------------------------------------------
# Alembic Config
# ---------------------------------------------------------------------------
config = context.config

# Override sqlalchemy.url from app settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our metadata for autogenerate support
target_metadata = Base.metadata

# Tables managed by packages/db (not by this backend app).
# Exclude them from autogenerate so Alembic doesn't try to drop them.
EXCLUDED_TABLES = {
    "customers",
    "products",
    "orders",
    "conversation_state",  # packages/db version (backend uses conversation_states)
}


def include_object(object, name, type_, reflected, compare_to):
    """Filter out tables that are managed outside the backend app."""
    if type_ == "table" and name in EXCLUDED_TABLES:
        return False
    return True


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to the database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
