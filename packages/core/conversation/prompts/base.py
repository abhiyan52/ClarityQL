"""Base prompt interface for intent classification."""

from abc import ABC, abstractmethod

from langchain_core.prompts import ChatPromptTemplate


class BaseIntentPrompt(ABC):
    """
    Abstract base class for intent classification prompts.

    All intent prompt versions must inherit from this class
    and implement the build method.
    """

    # Version identifier (e.g., "v1", "v2")
    version: str

    # Human-readable description of this prompt version
    description: str

    @abstractmethod
    def build(self) -> ChatPromptTemplate:
        """
        Build the intent classification prompt template.

        The template should expect the following variables:
        - previous_query_summary: Summary of the previous QueryAST
        - new_query: The new user query text

        Returns:
            A ChatPromptTemplate ready for use with an LLM.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} version={self.version}>"
