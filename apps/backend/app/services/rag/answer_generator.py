"""RAG answer generator service for generating natural language answers from chunks."""

import logging
from typing import List

from langchain_core.language_models import BaseChatModel

from packages.llm.factory import LLMFactory
from packages.llm.prompts.rag import RAGAnswerPromptRegistry

logger = logging.getLogger(__name__)


class RAGAnswerGenerator:
    """
    Service for generating natural language answers from RAG chunks.

    Uses LLM to synthesize retrieved document chunks into coherent answers.
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        prompt_version: str = "latest",
    ):
        """
        Initialize the RAG answer generator.

        Args:
            llm: LangChain chat model to use.
                Uses LLMFactory.create_from_settings() if not provided.
            prompt_version: Version of the prompt to use (e.g., "v1", "latest").
        """
        self._llm = llm or LLMFactory.create_from_settings()
        self._prompt = RAGAnswerPromptRegistry.get(prompt_version)

    def generate(
        self,
        query: str,
        chunks: List[dict],
        conversation_history: List[dict] | None = None,
    ) -> str:
        """
        Generate a natural language answer from retrieved chunks.

        Args:
            query: The user's query.
            chunks: List of chunk dictionaries with content, document_title, etc.
            conversation_history: Optional list of previous messages for context.

        Returns:
            Generated answer string. Returns empty string if no chunks provided
            or if generation fails.
        """
        if not chunks:
            return "I couldn't find any relevant information in the documents to answer your question."

        try:
            # Format chunks for context
            chunks_context = self._format_chunks_for_context(chunks)

            # Format conversation history if provided
            conversation_history_str = None
            if conversation_history:
                conversation_history_str = self._format_conversation_history(conversation_history)

            # Build prompt
            prompt_template = self._prompt.build(
                query=query,
                chunks_context=chunks_context,
                conversation_history=conversation_history_str,
            )

            # Invoke LLM
            messages = prompt_template.format_messages()
            response = self._llm.invoke(messages)
            answer = self._normalize_content(response.content)

            logger.info(f"Generated RAG answer for query: '{query[:50]}...' ({len(answer)} chars)")

            return answer

        except Exception as e:
            logger.error(f"Failed to generate RAG answer: {e}", exc_info=True)
            # Return fallback message instead of failing
            return "I encountered an error while generating an answer. However, I found some relevant document excerpts that might help answer your question."

    def _format_chunks_for_context(self, chunks: List[dict]) -> str:
        """
        Format chunks into a readable context string for the LLM.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            Formatted string with chunk content and metadata.
        """
        formatted_parts = []

        for i, chunk in enumerate(chunks, 1):
            parts = [f"[Excerpt {i}]"]

            # Add document title if available
            if chunk.get("document_title"):
                parts.append(f"Source: {chunk['document_title']}")

            # Add page number if available
            if chunk.get("page_number"):
                parts.append(f"Page: {chunk['page_number']}")

            # Add section if available
            if chunk.get("section"):
                parts.append(f"Section: {chunk['section']}")

            # Add similarity score if available (for debugging)
            if chunk.get("similarity_score"):
                score = chunk["similarity_score"]
                parts.append(f"Relevance: {score:.0%}")

            # Add content
            content = chunk.get("content", "").strip()
            if content:
                parts.append(f"\n{content}")

            formatted_parts.append("\n".join(parts))

        return "\n\n".join(formatted_parts)

    def _format_conversation_history(self, history: List[dict]) -> str:
        """
        Format conversation history for context.

        Args:
            history: List of message dictionaries with 'role' and 'content'.

        Returns:
            Formatted conversation history string.
        """
        formatted_parts = []

        for msg in history[-5:]:  # Only include last 5 messages for context
            role = msg.get("role", "unknown")
            content = msg.get("content", "").strip()

            if content:
                role_label = "User" if role == "user" else "Assistant"
                formatted_parts.append(f"{role_label}: {content}")

        return "\n".join(formatted_parts) if formatted_parts else ""

    def _normalize_content(self, content: str | list) -> str:
        """
        Normalize LLM response content.

        Args:
            content: Raw content from LLM (can be string or list of content blocks).

        Returns:
            Normalized content string.
        """
        if not content:
            return ""

        # Handle list of content blocks (some LLMs return structured content)
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    # Handle dict with 'text' or 'content' key
                    text = block.get("text") or block.get("content", "")
                    if text:
                        text_parts.append(str(text))
                elif isinstance(block, str):
                    text_parts.append(block)
                else:
                    # Try to convert to string
                    text_parts.append(str(block))
            content = " ".join(text_parts)

        # Ensure content is a string
        content = str(content)

        # Remove leading/trailing whitespace
        content = content.strip()

        # Remove markdown code blocks if present (sometimes LLMs wrap answers)
        if content.startswith("```") and content.endswith("```"):
            lines = content.split("\n")
            if len(lines) > 2:
                content = "\n".join(lines[1:-1])

        return content.strip()
