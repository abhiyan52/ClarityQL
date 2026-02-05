"""Intent classification prompts for ClarityQL."""

from packages.core.conversation.prompts.base import BaseIntentPrompt
from packages.core.conversation.prompts.registry import IntentPromptRegistry

# Import versions to trigger registration
from packages.core.conversation.prompts import versions  # noqa: F401

__all__ = [
    "BaseIntentPrompt",
    "IntentPromptRegistry",
]
