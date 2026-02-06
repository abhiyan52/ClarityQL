"""QueryLog model for tracking RAG queries and responses."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class QueryLog(Base):
    """
    Audit log for every RAG query a user makes.

    Tracks the original question, which documents and chunks were retrieved,
    the generated answer, latency, and model used. Useful for analytics,
    debugging retrieval quality, and building feedback loops.
    """

    __tablename__ = "query_logs"

    # ── Primary key ──────────────────────────
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # ── Tenant & user scope ──────────────────
    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Query ────────────────────────────────
    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
    )

    # ── Retrieval context ────────────────────
    document_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="IDs of documents used for retrieval",
    )
    chunk_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="IDs of chunks returned by similarity search",
    )

    # ── Response ─────────────────────────────
    answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    model_used: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="LLM model used for generation",
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="End-to-end latency in milliseconds",
    )

    # ── Extensible metadata ──────────────────
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional context (retrieval scores, prompt tokens, etc.)",
    )

    # ── Timestamp ────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ────────────────────────
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<QueryLog {self.id} user={self.user_id}>"
