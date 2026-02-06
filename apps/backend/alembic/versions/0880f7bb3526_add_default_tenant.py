"""add_default_tenant

Revision ID: 0880f7bb3526
Revises: 65fb84b2c6a2
Create Date: 2026-02-06 14:10:00.000000

Creates a default tenant for single-tenant usage.
All existing and new users without a tenant will be assigned to this tenant.
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Add backend directory to path to import constants
_ALEMBIC_DIR = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _ALEMBIC_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.constants import DEFAULT_TENANT_ID

# revision identifiers, used by Alembic.
revision: str = "0880f7bb3526"
down_revision: Union[str, Sequence[str], None] = "65fb84b2c6a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create default tenant and assign existing users to it."""

    # ── Insert default tenant ─────────────────────────────────────────
    op.execute(
        sa.text(f"""
        INSERT INTO tenants (id, name, slug, is_active, created_at, updated_at)
        VALUES (
            '{DEFAULT_TENANT_ID}'::uuid,
            'Default Organization',
            'default',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (slug) DO NOTHING
        """)
    )

    # ── Assign all existing users to default tenant ───────────────────
    op.execute(
        sa.text(f"""
        UPDATE users
        SET tenant_id = '{DEFAULT_TENANT_ID}'::uuid
        WHERE tenant_id IS NULL
        """)
    )

    # ── Make tenant_id NOT NULL (now that all users have a tenant) ────
    op.alter_column(
        "users",
        "tenant_id",
        existing_type=sa.UUID(),
        nullable=False,
    )


def downgrade() -> None:
    """Revert changes — make tenant_id nullable and remove default tenant."""

    # ── Make tenant_id nullable again ─────────────────────────────────
    op.alter_column(
        "users",
        "tenant_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # ── Remove default tenant ─────────────────────────────────────────
    op.execute(
        sa.text(f"""
        DELETE FROM tenants
        WHERE id = '{DEFAULT_TENANT_ID}'::uuid
        """)
    )
