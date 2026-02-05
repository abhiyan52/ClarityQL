"""Base prompt interface for ClarityQL."""

from abc import ABC, abstractmethod

from langchain_core.prompts import ChatPromptTemplate


class BasePrompt(ABC):
    """
    Abstract base class for NLQ parser prompts.

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
        schema_context: str,
        format_instructions: str,
    ) -> ChatPromptTemplate:
        """
        Build the prompt template.

        Args:
            schema_context: Description of available fields, tables, and metrics.
            format_instructions: Pydantic output parser format instructions.

        Returns:
            A ChatPromptTemplate ready for use with an LLM.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} version={self.version}>"
