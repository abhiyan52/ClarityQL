"""Conversation management for ClarityQL."""

from packages.core.conversation.intent_classifier import (
    IntentClassifier,
    IntentClassificationError,
    QueryIntent,
)
from packages.core.conversation.state import (
    ConversationContext,
    ConversationStateManager,
    get_state_manager,
)
from packages.core.conversation.ast_merge import (
    ASTMergeError,
    ast_diff,
    is_delta_empty,
    merge_ast,
)
from packages.core.conversation.prompts import (
    BaseIntentPrompt,
    IntentPromptRegistry,
)

__all__ = [
    # Intent classifier
    "IntentClassifier",
    "IntentClassificationError",
    "QueryIntent",
    # State management
    "ConversationContext",
    "ConversationStateManager",
    "get_state_manager",
    # AST merge
    "ASTMergeError",
    "ast_diff",
    "is_delta_empty",
    "merge_ast",
    # Prompts
    "BaseIntentPrompt",
    "IntentPromptRegistry",
]
