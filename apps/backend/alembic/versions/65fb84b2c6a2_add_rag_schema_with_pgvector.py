"""add_rag_schema_with_pgvector

Revision ID: 65fb84b2c6a2
Revises:
Create Date: 2026-02-06 13:55:15.633863

Adds:
- pgvector extension
- tenants table (multi-tenant isolation)
- tenant_id column on users table
- documents table (RAG document storage)
- chunks table (document chunks + pgvector embeddings with HNSW index)
- query_logs table (RAG query audit trail)
"""

from typing import Sequence, Union

import pgvector.sqlalchemy.vector
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "65fb84b2c6a2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — add RAG tables with pgvector support."""

    # ── Enable pgvector extension ─────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── tenants ───────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=True)

    # ── users.tenant_id ───────────────────────────────────────────────
    op.add_column("users", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_foreign_key(
        "fk_users_tenant_id",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── documents ─────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.UUID(),
            nullable=True,
            comment="NULL for system / global documents",
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source_type",
            sa.Enum(
                "uploaded",
                "system",
                "web",
                name="document_source_type",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "visibility",
            sa.Enum(
                "private",
                "tenant",
                "global",
                name="document_visibility",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "storage_path",
            sa.String(length=1024),
            nullable=True,
            comment="Path in object storage or local filesystem",
        ),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column(
            "checksum",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hash for deduplication",
        ),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Auto-expiry for temporary documents",
        ),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            comment="Denormalized count of chunks for quick lookup",
        ),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Arbitrary key-value metadata (tags, source URL, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name="ck_documents_version_positive"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "checksum", name="uq_documents_tenant_checksum"
        ),
    )
    op.create_index(
        op.f("ix_documents_checksum"), "documents", ["checksum"], unique=False
    )
    op.create_index(
        op.f("ix_documents_owner_user_id"),
        "documents",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_tenant_id"), "documents", ["tenant_id"], unique=False
    )

    # ── query_logs ────────────────────────────────────────────────────
    op.create_table(
        "query_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column(
            "document_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=True,
            comment="IDs of documents used for retrieval",
        ),
        sa.Column(
            "chunk_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=True,
            comment="IDs of chunks returned by similarity search",
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "model_used",
            sa.String(length=100),
            nullable=True,
            comment="LLM model used for generation",
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
            comment="End-to-end latency in milliseconds",
        ),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Additional context (retrieval scores, prompt tokens, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_query_logs_tenant_id"), "query_logs", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_query_logs_user_id"), "query_logs", ["user_id"], unique=False
    )

    # ── chunks (with pgvector embedding) ──────────────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            comment="0-based position of this chunk within the document",
        ),
        sa.Column(
            "page_number",
            sa.Integer(),
            nullable=True,
            comment="Source page number (PDF, DOCX, etc.)",
        ),
        sa.Column(
            "section",
            sa.String(length=500),
            nullable=True,
            comment="Section heading or label this chunk belongs to",
        ),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Raw text content of the chunk",
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=True,
            comment="Number of tokens (useful for prompt budgeting)",
        ),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.vector.VECTOR(dim=1024),
            nullable=True,
            comment="Dense vector from embedding model (e.g. BGE-large 1024-dim)",
        ),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Arbitrary chunk-level metadata",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False
    )
    op.create_index(
        "ix_chunks_document_index",
        "chunks",
        ["document_id", "chunk_index"],
        unique=True,
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_chunks_tenant_document",
        "chunks",
        ["tenant_id", "document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chunks_tenant_id"), "chunks", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema — remove RAG tables and pgvector extension."""

    # ── Drop chunks ───────────────────────────────────────────────────
    op.drop_index(op.f("ix_chunks_tenant_id"), table_name="chunks")
    op.drop_index("ix_chunks_tenant_document", table_name="chunks")
    op.drop_index(
        "ix_chunks_embedding_hnsw",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_chunks_document_index", table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")

    # ── Drop query_logs ───────────────────────────────────────────────
    op.drop_index(op.f("ix_query_logs_user_id"), table_name="query_logs")
    op.drop_index(op.f("ix_query_logs_tenant_id"), table_name="query_logs")
    op.drop_table("query_logs")

    # ── Drop documents ────────────────────────────────────────────────
    op.drop_index(op.f("ix_documents_tenant_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_owner_user_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_checksum"), table_name="documents")
    op.drop_table("documents")

    # ── Drop users.tenant_id ──────────────────────────────────────────
    op.drop_constraint("fk_users_tenant_id", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_column("users", "tenant_id")

    # ── Drop tenants ──────────────────────────────────────────────────
    op.drop_index(op.f("ix_tenants_slug"), table_name="tenants")
    op.drop_table("tenants")

    # ── Drop enum types ───────────────────────────────────────────────
    op.execute("DROP TYPE IF EXISTS document_source_type")
    op.execute("DROP TYPE IF EXISTS document_visibility")

    # ── Drop pgvector extension ───────────────────────────────────────
    op.execute("DROP EXTENSION IF EXISTS vector")
