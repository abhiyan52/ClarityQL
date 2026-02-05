"""ConversationState model for AST persistence."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ConversationState(Base):
    """
    Stores the current QueryAST for a conversation.

    This is the conversational memory - AST is the single source of truth.
    We do NOT store SQL, results, or chat history.
    """

    __tablename__ = "conversation_states"

    conversation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ast_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="state",
    )

    def __repr__(self) -> str:
        return f"<ConversationState conversation_id={self.conversation_id}>"
