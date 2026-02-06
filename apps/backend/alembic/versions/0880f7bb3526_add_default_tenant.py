"""add_default_tenant

Revision ID: 0880f7bb3526
Revises: 65fb84b2c6a2
Create Date: 2026-02-06 14:10:00.000000

Creates a default tenant for single-tenant usage.
All existing and new users without a tenant will be assigned to this tenant.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0880f7bb3526"
down_revision: Union[str, Sequence[str], None] = "65fb84b2c6a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default tenant UUID (fixed for consistency across environments)
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Create default tenant and assign existing users to it."""

    # ── Insert default tenant ─────────────────────────────────────────
    op.execute(
        sa.text("""
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
            "tenant_id": DEFAULT_TENANT_ID,
            "name": "Default Organization",
            "slug": "default",
            "is_active": True,
        },
    )

    # ── Assign all existing users to default tenant ───────────────────
    op.execute(
        sa.text("""
        UPDATE users
        SET tenant_id = :tenant_id::uuid
        WHERE tenant_id IS NULL
        """),
        {"tenant_id": DEFAULT_TENANT_ID},
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
        sa.text("""
        DELETE FROM tenants
        WHERE id = :tenant_id::uuid
        """),
        {"tenant_id": DEFAULT_TENANT_ID},
    )
