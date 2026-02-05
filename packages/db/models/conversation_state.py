"""Conversation state model for NLQ context persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.db.base import Base


class ConversationState(Base):
    """Represents stored context for an NLQ conversation."""

    __tablename__ = "conversation_state"

    conversation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.conversation_id"), primary_key=True
    )
    ast_json: Mapped[dict] = mapped_column(JSONB, nullable=True)
    last_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conversation = relationship("Conversation", back_populates="state")
