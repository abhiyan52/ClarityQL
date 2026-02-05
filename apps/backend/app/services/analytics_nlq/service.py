"""Service layer for analytics NLQ processing."""

from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel

from packages.core.conversation import (
    ConversationStateManager,
    IntentClassifier,
    QueryIntent,
    get_state_manager,
    merge_ast,
)
from packages.core.safety.validator import ASTValidationError, ASTValidator
from packages.core.schema_registry.registry import SchemaRegistry, get_default_registry
from packages.core.sql_ast.join_resolver import JoinPlan, JoinResolutionError, JoinResolver
from packages.core.sql_ast.models import QueryAST
from packages.llm.factory import LLMFactory
from packages.llm.parser import NLQParseError, NLQParser


# -----------------------------
# Result Types
# -----------------------------


@dataclass
class NLQProcessingResult:
    """Result of processing an NLQ query."""

    success: bool
    ast: QueryAST | None = None
    join_plan: JoinPlan | None = None
    error: str | None = None
    error_type: str | None = None
    # Conversation context
    intent: QueryIntent | None = None
    previous_ast: QueryAST | None = None
    merged: bool = False


# -----------------------------
# Service
# -----------------------------


class AnalyticsNLQService:
    """
    Service for processing natural language analytics queries.

    Orchestrates the full pipeline:
    1. Parse NLQ to QueryAST (via LLM)
    2. Validate the AST against schema
    3. Resolve required joins
    """

    def __init__(
        self,
        registry: SchemaRegistry | None = None,
        parser: NLQParser | None = None,
        validator: ASTValidator | None = None,
        resolver: JoinResolver | None = None,
    ):
        """
        Initialize the service.

        All dependencies can be injected for testing. Uses defaults if not provided.
        """
        self._registry = registry or get_default_registry()
        self._parser = parser or NLQParser(registry=self._registry)
        self._validator = validator or ASTValidator(registry=self._registry)
        self._resolver = resolver or JoinResolver(registry=self._registry)

    def process_query(self, query: str) -> NLQProcessingResult:
        """
        Process a natural language query through the full pipeline.

        Args:
            query: The user's natural language query.

        Returns:
            NLQProcessingResult with success status and either
            the processed AST/JoinPlan or error information.
        """
        # Step 1: Parse NLQ to AST
        try:
            ast = self._parser.parse(query)
        except NLQParseError as e:
            return NLQProcessingResult(
                success=False,
                error=str(e),
                error_type="parse_error",
            )

        # Step 2: Validate AST
        try:
            self._validator.validate(ast)
        except ASTValidationError as e:
            return NLQProcessingResult(
                success=False,
                ast=ast,
                error=str(e),
                error_type="validation_error",
            )

        # Step 3: Resolve joins
        try:
            join_plan = self._resolver.resolve(ast)
        except JoinResolutionError as e:
            return NLQProcessingResult(
                success=False,
                ast=ast,
                error=str(e),
                error_type="join_resolution_error",
            )

        return NLQProcessingResult(
            success=True,
            ast=ast,
            join_plan=join_plan,
        )

    def parse_only(self, query: str) -> QueryAST:
        """
        Parse a query without validation or join resolution.

        Useful for debugging or when you want to handle
        validation separately.

        Args:
            query: The user's natural language query.

        Returns:
            The parsed QueryAST.

        Raises:
            NLQParseError: If parsing fails.
        """
        return self._parser.parse(query)


# -----------------------------
# Conversational Service
# -----------------------------


class ConversationalNLQService:
    """
    NLQ service with conversational memory.

    Enables follow-up queries to refine previous results by:
    1. Classifying intent (REFINE vs RESET)
    2. Merging delta AST with previous context
    3. Storing merged AST for future queries

    AST is the single source of truth for conversation state.
    """

    def __init__(
        self,
        registry: SchemaRegistry | None = None,
        parser: NLQParser | None = None,
        validator: ASTValidator | None = None,
        resolver: JoinResolver | None = None,
        state_manager: ConversationStateManager | None = None,
        llm: BaseChatModel | None = None,
    ):
        """
        Initialize the conversational service.

        All dependencies can be injected for testing.
        """
        self._registry = registry or get_default_registry()
        self._llm = llm or LLMFactory.create_from_settings()
        self._parser = parser or NLQParser(registry=self._registry, llm=self._llm)
        self._validator = validator or ASTValidator(registry=self._registry)
        self._resolver = resolver or JoinResolver(registry=self._registry)
        self._state = state_manager or get_state_manager()
        self._classifier = IntentClassifier(llm=self._llm)

    def process_query(
        self,
        query: str,
        conversation_id: str,
    ) -> NLQProcessingResult:
        """
        Process a query with conversational context.

        Args:
            query: The user's natural language query.
            conversation_id: Unique identifier for the conversation.

        Returns:
            NLQProcessingResult with the merged AST and context info.
        """
        # Step 1: Load previous context
        previous_ast = self._state.get(conversation_id)

        # Step 2: Classify intent
        try:
            intent = self._classifier.classify(query, previous_ast)
        except Exception:
            # On classification failure, default to RESET
            intent = QueryIntent.RESET

        # Step 3: Parse the query
        try:
            parsed_ast = self._parser.parse(query)
        except NLQParseError as e:
            return NLQProcessingResult(
                success=False,
                error=str(e),
                error_type="parse_error",
                intent=intent,
                previous_ast=previous_ast,
            )

        # Step 4: Merge or reset based on intent
        merged = False
        final_ast = parsed_ast

        if intent == QueryIntent.REFINE and previous_ast is not None:
            try:
                final_ast = merge_ast(previous_ast, parsed_ast)
                merged = True
            except Exception:
                # Merge failed - fall back to parsed AST
                final_ast = parsed_ast
                merged = False

        # Step 5: Validate the final AST
        validation_error = self._validator.validate(final_ast)
        if validation_error:
            # If merged AST is invalid, try falling back to parsed AST
            if merged:
                fallback_error = self._validator.validate(parsed_ast)
                if fallback_error is None:
                    final_ast = parsed_ast
                    merged = False
                else:
                    return NLQProcessingResult(
                        success=False,
                        ast=final_ast,
                        error=validation_error,
                        error_type="validation_error",
                        intent=intent,
                        previous_ast=previous_ast,
                        merged=merged,
                    )
            else:
                return NLQProcessingResult(
                    success=False,
                    ast=final_ast,
                    error=validation_error,
                    error_type="validation_error",
                    intent=intent,
                    previous_ast=previous_ast,
                    merged=merged,
                )

        # Step 6: Resolve joins
        try:
            join_plan = self._resolver.resolve(final_ast)
        except JoinResolutionError as e:
            return NLQProcessingResult(
                success=False,
                ast=final_ast,
                error=str(e),
                error_type="join_resolution_error",
                intent=intent,
                previous_ast=previous_ast,
                merged=merged,
            )

        # Step 7: Store the final AST for future queries
        self._state.set(conversation_id, final_ast)

        return NLQProcessingResult(
            success=True,
            ast=final_ast,
            join_plan=join_plan,
            intent=intent,
            previous_ast=previous_ast,
            merged=merged,
        )

    def clear_context(self, conversation_id: str) -> None:
        """Clear the conversation context."""
        self._state.clear(conversation_id)

    def get_context(self, conversation_id: str) -> QueryAST | None:
        """Get the current context for a conversation."""
        return self._state.get(conversation_id)


# -----------------------------
# Legacy function (for backwards compatibility)
# -----------------------------


def queue_query(query: str) -> str:
    """Queue an NLQ query for processing (placeholder)."""
    return "pending"
