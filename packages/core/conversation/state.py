"""
Conversation State Manager for ClarityQL.

Manages the storage and retrieval of QueryAST per conversation.
AST is the single source of truth for conversational context.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock

from packages.core.sql_ast.models import QueryAST


@dataclass
class ConversationContext:
    """Context for a single conversation."""

    conversation_id: str
    last_ast: QueryAST | None = None
    last_updated: datetime = field(default_factory=datetime.now)
    query_count: int = 0

    def update(self, ast: QueryAST) -> None:
        """Update the context with a new AST."""
        self.last_ast = ast
        self.last_updated = datetime.now()
        self.query_count += 1

    def is_stale(self, max_age: timedelta) -> bool:
        """Check if the context is older than max_age."""
        return datetime.now() - self.last_updated > max_age


class ConversationStateManager:
    """
    Thread-safe manager for conversation state.

    Stores the last QueryAST for each conversation, enabling
    follow-up queries to refine previous results.

    Note: This is an in-memory implementation. For production,
    consider using Redis or a database for persistence.
    """

    def __init__(
        self,
        max_age: timedelta = timedelta(hours=1),
        max_conversations: int = 1000,
    ):
        """
        Initialize the state manager.

        Args:
            max_age: Maximum age before a conversation is considered stale.
            max_conversations: Maximum number of conversations to track.
        """
        self._state: dict[str, ConversationContext] = {}
        self._lock = Lock()
        self._max_age = max_age
        self._max_conversations = max_conversations

    def get(self, conversation_id: str) -> QueryAST | None:
        """
        Get the last AST for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            The last QueryAST, or None if no context exists or it's stale.
        """
        with self._lock:
            context = self._state.get(conversation_id)

            if context is None:
                return None

            # Check for staleness
            if context.is_stale(self._max_age):
                del self._state[conversation_id]
                return None

            return context.last_ast

    def set(self, conversation_id: str, ast: QueryAST) -> None:
        """
        Store an AST for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
            ast: The QueryAST to store.
        """
        with self._lock:
            # Cleanup if at capacity
            if len(self._state) >= self._max_conversations:
                self._cleanup_stale()

            if conversation_id in self._state:
                self._state[conversation_id].update(ast)
            else:
                self._state[conversation_id] = ConversationContext(
                    conversation_id=conversation_id,
                    last_ast=ast,
                    query_count=1,
                )

    def clear(self, conversation_id: str) -> None:
        """
        Clear the context for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
        """
        with self._lock:
            self._state.pop(conversation_id, None)

    def get_context(self, conversation_id: str) -> ConversationContext | None:
        """
        Get the full context object for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            The ConversationContext, or None if not found.
        """
        with self._lock:
            return self._state.get(conversation_id)

    def _cleanup_stale(self) -> None:
        """Remove stale conversations. Must be called with lock held."""
        stale_ids = [
            cid for cid, ctx in self._state.items()
            if ctx.is_stale(self._max_age)
        ]
        for cid in stale_ids:
            del self._state[cid]

        # If still at capacity, remove oldest
        if len(self._state) >= self._max_conversations:
            oldest = min(
                self._state.items(),
                key=lambda x: x[1].last_updated
            )
            del self._state[oldest[0]]


# Global instance for convenience
_default_state_manager: ConversationStateManager | None = None


def get_state_manager() -> ConversationStateManager:
    """Get the default state manager instance."""
    global _default_state_manager
    if _default_state_manager is None:
        _default_state_manager = ConversationStateManager()
    return _default_state_manager
