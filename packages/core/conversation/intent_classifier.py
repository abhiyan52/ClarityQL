"""
Intent Classifier for ClarityQL.

Classifies user queries as REFINE (modify previous query) or RESET (start new query).
This enables conversational context without implicit memory.
"""

from enum import Enum

from langchain_core.language_models import BaseChatModel

from packages.core.conversation.prompts import IntentPromptRegistry
from packages.core.sql_ast.models import QueryAST


class QueryIntent(str, Enum):
    """Classification of user query intent."""

    REFINE = "refine"  # Modify/filter previous query
    RESET = "reset"  # Start a completely new query


class IntentClassificationError(Exception):
    """Raised when intent classification fails."""

    pass


class IntentClassifier:
    """
    Classifies whether a new query refines the previous one or starts fresh.

    Uses structured LLM output to make a binary decision based on:
    - The previous query's AST summary
    - The new user query text

    Supports prompt versioning for A/B testing and iteration.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        prompt_version: str = "latest",
    ):
        """
        Initialize the intent classifier.

        Args:
            llm: LangChain chat model to use for classification.
            prompt_version: Version of the prompt to use (e.g., "v1", "latest").
        """
        self._llm = llm
        self._prompt_version = prompt_version
        self._prompt_template = IntentPromptRegistry.get(prompt_version).build()

    @property
    def prompt_version(self) -> str:
        """Get the current prompt version."""
        return self._prompt_version

    def classify(
        self,
        new_query: str,
        previous_ast: QueryAST | None,
    ) -> QueryIntent:
        """
        Classify the intent of a new query.

        Args:
            new_query: The user's new natural language query.
            previous_ast: The AST from the previous query (if any).

        Returns:
            QueryIntent.REFINE if the query modifies the previous one.
            QueryIntent.RESET if the query starts a new analysis.
        """
        # No previous context = always RESET
        if previous_ast is None:
            return QueryIntent.RESET

        # Build context summary from previous AST
        ast_summary = self._summarize_ast(previous_ast)

        try:
            chain = self._prompt_template | self._llm
            response = chain.invoke({
                "previous_query_summary": ast_summary,
                "new_query": new_query,
            })

            # Parse the response - handle various LLM response formats
            result = self._extract_text(response.content)

            if "refine" in result:
                return QueryIntent.REFINE
            elif "reset" in result:
                return QueryIntent.RESET
            else:
                # Default to RESET if unclear
                return QueryIntent.RESET

        except Exception as e:
            raise IntentClassificationError(
                f"Failed to classify intent: {e}"
            ) from e

    def _extract_text(self, content) -> str:
        """
        Extract text content from various LLM response formats.

        Handles:
        - Plain string responses
        - Gemini's structured content blocks
        - Other list-based formats
        """
        if isinstance(content, str):
            return content.strip().lower()

        if isinstance(content, list):
            # Extract text from content blocks (e.g., Gemini format)
            text_parts = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            return " ".join(text_parts).strip().lower()

        # Fallback: convert to string
        return str(content).strip().lower()

    def _summarize_ast(self, ast: QueryAST) -> str:
        """Create a human-readable summary of the AST for the classifier."""
        lines = []

        # Metrics
        metrics_str = ", ".join(
            f"{m.function.value}({m.field})" for m in ast.metrics
        )
        lines.append(f"metrics: {metrics_str}")

        # Dimensions
        if ast.dimensions:
            dims_str = ", ".join(d.field for d in ast.dimensions)
            lines.append(f"dimensions: [{dims_str}]")

        # Filters
        if ast.filters:
            filters_str = ", ".join(
                f"{f.field} {f.operator.value} {f.value}" for f in ast.filters
            )
            lines.append(f"filters: [{filters_str}]")

        # Order
        if ast.order_by:
            order_str = ", ".join(
                f"{o.field} {o.direction.value}" for o in ast.order_by
            )
            lines.append(f"order_by: [{order_str}]")

        # Limit
        if ast.limit != 50:  # Only show if not default
            lines.append(f"limit: {ast.limit}")

        return "\n".join(lines)
