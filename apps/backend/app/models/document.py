"""Document model for RAG document storage."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

import enum


class DocumentSourceType(str, enum.Enum):
    """How the document was ingested."""

    UPLOADED = "uploaded"
    SYSTEM = "system"
    WEB = "web"


class DocumentVisibility(str, enum.Enum):
    """Who can see / query the document."""

    PRIVATE = "private"  # Only owner
    TENANT = "tenant"  # All users in the tenant
    GLOBAL = "global"  # All users across tenants (system docs)


class DocumentProcessingStatus(str, enum.Enum):
    """Processing status for document ingestion pipeline."""

    UPLOADED = "uploaded"  # File uploaded, not yet processed
    PARSING = "parsing"  # Document is being parsed (Docling)
    PARSED = "parsed"  # Document parsed successfully
    CHUNKING = "chunking"  # Document is being chunked
    CHUNKED = "chunked"  # Document chunked successfully
    EMBEDDING = "embedding"  # Embeddings are being generated
    READY = "ready"  # Document is fully processed and ready for search
    FAILED = "failed"  # Processing failed at any stage


# ──────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────


class Document(Base):
    """
    A document stored for RAG retrieval.

    Supports uploaded, system-default, and web-scraped documents.
    Scoped to a tenant, optionally owned by a user.
    Supports versioning, visibility control, and deduplication via checksum.
    """

    __tablename__ = "documents"
    __table_args__ = (
        # Prevent duplicate files within a tenant (same checksum = same file)
        UniqueConstraint("tenant_id", "checksum", name="uq_documents_tenant_checksum"),
        CheckConstraint("version >= 1", name="ck_documents_version_positive"),
    )

    # ── Primary key ──────────────────────────
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # ── Tenant & ownership ───────────────────
    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="NULL for system / global documents",
    )

    # ── Document metadata ────────────────────
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    source_type: Mapped[DocumentSourceType] = mapped_column(
        Enum(DocumentSourceType, name="document_source_type", create_constraint=True),
        nullable=False,
        default=DocumentSourceType.UPLOADED,
    )
    visibility: Mapped[DocumentVisibility] = mapped_column(
        Enum(DocumentVisibility, name="document_visibility", create_constraint=True),
        nullable=False,
        default=DocumentVisibility.TENANT,
    )

    # ── File / storage ───────────────────────
    storage_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Path in object storage or local filesystem",
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA-256 hash for deduplication",
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # ── Versioning & language ────────────────
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
    )

    # ── Lifecycle ────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        Enum(DocumentProcessingStatus, name="document_processing_status", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DocumentProcessingStatus.UPLOADED,
        index=True,
        comment="Current stage in the ingestion pipeline",
    )
    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if processing failed",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Auto-expiry for temporary documents",
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Denormalized count of chunks for quick lookup",
    )

    # ── Extensible metadata ──────────────────
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Arbitrary key-value metadata (tags, source URL, etc.)",
    )

    # ── Timestamps ───────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ────────────────────────
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="documents",
    )
    owner: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[owner_user_id],
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )

    def __repr__(self) -> str:
        return f"<Document {self.title!r} v{self.version}>"
