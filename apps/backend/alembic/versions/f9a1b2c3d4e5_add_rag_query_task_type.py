"""Add RAG_QUERY task type

Revision ID: f9a1b2c3d4e5
Revises: a5de6bfa025f
Create Date: 2026-02-08 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f9a1b2c3d4e5'
down_revision: Union[str, None] = 'a5de6bfa025f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new enum value to task_type
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'RAG_QUERY'")


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values
    # This is intentionally left empty
    pass
