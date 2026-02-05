"""Service layer for analytics NLQ processing."""

from dataclasses import dataclass

from packages.core.safety.validator import ASTValidationError, ASTValidator
from packages.core.schema_registry.registry import SchemaRegistry, get_default_registry
from packages.core.sql_ast.join_resolver import JoinPlan, JoinResolutionError, JoinResolver
from packages.core.sql_ast.models import QueryAST
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
# Legacy function (for backwards compatibility)
# -----------------------------


def queue_query(query: str) -> str:
    """Queue an NLQ query for processing (placeholder)."""
    return "pending"
