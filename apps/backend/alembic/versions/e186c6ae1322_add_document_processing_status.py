"""add_document_processing_status

Revision ID: e186c6ae1322
Revises: 21cfdfadc4b3
Create Date: 2026-02-07 02:28:32.186005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e186c6ae1322'
down_revision: Union[str, None] = '21cfdfadc4b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for document processing status
    op.execute("""
        CREATE TYPE document_processing_status AS ENUM (
            'uploaded', 'parsing', 'parsed', 'chunking', 'chunked', 'embedding', 'ready', 'failed'
        )
    """)
    
    # Add processing_status column
    op.add_column(
        'documents',
        sa.Column(
            'processing_status',
            sa.Enum(
                'uploaded', 'parsing', 'parsed', 'chunking', 'chunked', 'embedding', 'ready', 'failed',
                name='document_processing_status',
                create_type=False
            ),
            nullable=False,
            server_default='uploaded'
        )
    )
    
    # Add processing_error column
    op.add_column(
        'documents',
        sa.Column('processing_error', sa.Text(), nullable=True)
    )
    
    # Create index on processing_status for efficient queries
    op.create_index(
        'ix_documents_processing_status',
        'documents',
        ['processing_status']
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_documents_processing_status', table_name='documents')
    
    # Drop columns
    op.drop_column('documents', 'processing_error')
    op.drop_column('documents', 'processing_status')
    
    # Drop enum type
    op.execute('DROP TYPE document_processing_status')
