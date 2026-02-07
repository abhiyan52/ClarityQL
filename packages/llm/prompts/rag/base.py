"""Base prompt interface for RAG answer generation."""

from abc import ABC, abstractmethod

from langchain_core.prompts import ChatPromptTemplate


class BaseRAGAnswerPrompt(ABC):
    """
    Abstract base class for RAG answer generation prompts.

    All prompt versions must inherit from this class and implement
    the build method.
    """

    # Version identifier (e.g., "v1", "v2")
    version: str

    # Human-readable description of this prompt version
    description: str

    @abstractmethod
    def build(
        self,
        query: str,
        chunks_context: str,
        conversation_history: str | None = None,
    ) -> ChatPromptTemplate:
        """
        Build the prompt template.

        Args:
            query: The user's query.
            chunks_context: Formatted context from retrieved chunks.
            conversation_history: Optional conversation history for context.

        Returns:
            A ChatPromptTemplate ready for use with an LLM.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} version={self.version}>"
