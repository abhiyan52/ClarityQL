"""Chunk model for RAG document chunks with pgvector embeddings."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Embedding dimension — BGE-large produces 1024-dim vectors.
# Change this constant if you switch embedding models.
EMBEDDING_DIMENSION = 1024


class Chunk(Base):
    """
    A single chunk of a document, with its embedding vector.

    Each chunk stores the raw text, positional metadata, and a dense
    vector embedding for similarity search via pgvector.

    Cosine similarity search uses the <=> operator (pgvector cosine distance).
    An HNSW index is created on the embedding column for fast ANN queries.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        # ── Composite index for tenant-scoped chunk lookup ──
        Index("ix_chunks_tenant_document", "tenant_id", "document_id"),
        # ── Unique chunk position within a document ──
        Index(
            "ix_chunks_document_index",
            "document_id",
            "chunk_index",
            unique=True,
        ),
        # ── HNSW index on embedding for cosine similarity search ──
        # HNSW gives better recall than IVFFLAT and doesn't need a
        # pre-built list count. Use `m=16, ef_construction=64` as sane defaults.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    # ── Primary key ──────────────────────────
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # ── Parent references (denormalized tenant_id for fast filtering) ──
    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Positional metadata ──────────────────
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based position of this chunk within the document",
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Source page number (PDF, DOCX, etc.)",
    )
    section: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Section heading or label this chunk belongs to",
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
    )

    # ── Content ──────────────────────────────
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw text content of the chunk",
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of tokens (useful for prompt budgeting)",
    )

    # ── Embedding (pgvector) ─────────────────
    embedding: Mapped[Any] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
        comment="Dense vector from embedding model (e.g. BGE-large 1024-dim)",
    )

    # ── Extensible metadata ──────────────────
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Arbitrary chunk-level metadata",
    )

    # ── Timestamps ───────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ────────────────────────
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<Chunk doc={self.document_id} idx={self.chunk_index}>"
