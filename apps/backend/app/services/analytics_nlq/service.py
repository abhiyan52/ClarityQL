"""
NLQ Analytics Service.

Orchestrates the full NLQ pipeline with conversational memory:
1. Load previous AST (if conversation exists)
2. Classify intent (REFINE/RESET)
3. Parse query to AST
4. Merge AST if REFINE
5. Validate AST
6. Resolve joins
7. Compile SQL
8. Execute query
9. Persist AST
10. Return results with explainability
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.conversation import (
    IntentClassifier,
    QueryIntent,
    merge_ast,
)
from packages.core.explainability import ExplainabilityBuilder
from packages.core.safety.validator import ASTValidationError, ASTValidator
from packages.core.schema_registry.registry import SchemaRegistry, get_default_registry
from packages.core.sql_ast.compiler import SQLCompiler
from packages.core.sql_ast.join_resolver import JoinPlan, JoinResolver
from packages.core.sql_ast.models import QueryAST
from packages.core.viz_inference import VisualizationSpec, infer_visualization
from packages.llm.factory import LLMFactory
from packages.llm.parser import NLQParser

from app.models.conversation import Conversation
from app.models.conversation_state import ConversationState
from app.services.analytics_nlq.execution import (
    ExecutionResult,
    execute_query,
    get_sql_string,
)


@dataclass
class NLQResult:
    """Complete result of NLQ processing."""

    success: bool
    conversation_id: UUID
    ast: QueryAST | None = None
    join_plan: JoinPlan | None = None
    sql: str | None = None
    execution_result: ExecutionResult | None = None
    explainability: dict | None = None
    visualization: VisualizationSpec | None = None
    intent: QueryIntent | None = None
    merged: bool = False
    error: str | None = None
    error_type: str | None = None


class NLQService:
    """
    Service for processing NLQ queries with conversational memory.

    This service orchestrates the full pipeline from natural language
    to executed SQL results, maintaining conversation state in the database.
    """

    def __init__(
        self,
        registry: SchemaRegistry | None = None,
        sqlalchemy_tables: dict | None = None,
    ):
        """
        Initialize the NLQ service.

        Args:
            registry: Schema registry for field metadata.
            sqlalchemy_tables: Dict of SQLAlchemy Table objects for compilation.
        """
        self._registry = registry or get_default_registry()
        self._llm = LLMFactory.create_from_settings()
        self._parser = NLQParser(registry=self._registry, llm=self._llm)
        self._validator = ASTValidator(registry=self._registry)
        self._resolver = JoinResolver(registry=self._registry)
        self._classifier = IntentClassifier(llm=self._llm)
        self._explainability = ExplainabilityBuilder()

        # SQLAlchemy tables for compilation
        self._tables = sqlalchemy_tables or self._create_default_tables()
        self._compiler = SQLCompiler(
            sqlalchemy_tables=self._tables,
            registry=self._registry,
        )

    async def process_query(
        self,
        query: str,
        user_id: UUID,
        session: AsyncSession,
        conversation_id: UUID | None = None,
    ) -> NLQResult:
        """
        Process a natural language query with full pipeline.

        Args:
            query: The user's natural language query.
            user_id: The authenticated user's ID.
            session: Async database session.
            conversation_id: Optional existing conversation ID.

        Returns:
            NLQResult with all processing results.
        """
        # Step 1: Get or create conversation
        conversation, previous_ast = await self._get_or_create_conversation(
            session, user_id, conversation_id
        )

        # Step 2: Classify intent
        try:
            intent = self._classifier.classify(query, previous_ast)
        except Exception:
            intent = QueryIntent.RESET

        # Step 3: Parse query to AST
        try:
            parsed_ast = self._parser.parse(query)
        except Exception as e:
            return NLQResult(
                success=False,
                conversation_id=conversation.id,
                intent=intent,
                error=str(e),
                error_type="parse_error",
            )

        # Step 4: Merge if REFINE
        merged = False
        final_ast = parsed_ast

        if intent == QueryIntent.REFINE and previous_ast is not None:
            try:
                final_ast = merge_ast(previous_ast, parsed_ast)
                merged = True
            except Exception:
                final_ast = parsed_ast
                merged = False

        # Step 5: Validate AST
        validation_error = self._validate_ast(final_ast)
        if validation_error:
            # Try fallback to parsed AST if merge caused issues
            if merged:
                fallback_error = self._validate_ast(parsed_ast)
                if fallback_error is None:
                    final_ast = parsed_ast
                    merged = False
                    validation_error = None
                else:
                    validation_error = fallback_error

        # Retry parsing once with validation feedback if still invalid
        if validation_error:
            retry_ast = self._retry_parse_with_validation_feedback(
                query=query,
                validation_error=validation_error,
            )
            if retry_ast is not None:
                retry_error = self._validate_ast(retry_ast)
                if retry_error is None:
                    final_ast = retry_ast
                    merged = False
                    validation_error = None
                else:
                    validation_error = retry_error

        if validation_error:
            return NLQResult(
                success=False,
                conversation_id=conversation.id,
                ast=final_ast,
                intent=intent,
                merged=merged,
                error=validation_error,
                error_type="validation_error",
            )

        # Step 6: Resolve joins
        try:
            join_plan = self._resolver.resolve(final_ast)
        except Exception as e:
            return NLQResult(
                success=False,
                conversation_id=conversation.id,
                ast=final_ast,
                intent=intent,
                merged=merged,
                error=str(e),
                error_type="join_resolution_error",
            )

        # Step 7: Compile SQL
        try:
            statement = self._compiler.compile(final_ast, join_plan)
            sql_string = get_sql_string(statement)
        except Exception as e:
            return NLQResult(
                success=False,
                conversation_id=conversation.id,
                ast=final_ast,
                join_plan=join_plan,
                intent=intent,
                merged=merged,
                error=str(e),
                error_type="compilation_error",
            )

        # Step 8: Execute query
        try:
            execution_result = await execute_query(session, statement)
        except Exception as e:
            return NLQResult(
                success=False,
                conversation_id=conversation.id,
                ast=final_ast,
                join_plan=join_plan,
                sql=sql_string,
                intent=intent,
                merged=merged,
                error=str(e),
                error_type="execution_error",
            )

        # Step 9: Build explainability
        explanation = self._explainability.build(final_ast, join_plan)

        # Step 10: Infer visualization from AST
        visualization = infer_visualization(final_ast, self._registry)

        # Step 11: Persist AST
        await self._save_conversation_state(session, conversation.id, final_ast)

        return NLQResult(
            success=True,
            conversation_id=conversation.id,
            ast=final_ast,
            join_plan=join_plan,
            sql=sql_string,
            execution_result=execution_result,
            explainability=explanation.to_dict(),
            visualization=visualization,
            intent=intent,
            merged=merged,
        )

    async def reset_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        session: AsyncSession,
    ) -> bool:
        """
        Reset a conversation by clearing its state.

        Args:
            conversation_id: The conversation to reset.
            user_id: The user making the request (for ownership check).
            session: Database session.

        Returns:
            True if reset successful, False if conversation not found.

        Raises:
            PermissionError: If user doesn't own the conversation.
        """
        # Fetch conversation with ownership check
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            return False

        if conversation.user_id != user_id:
            raise PermissionError("Not authorized to access this conversation")

        # Delete state
        state_result = await session.execute(
            select(ConversationState).where(
                ConversationState.conversation_id == conversation_id
            )
        )
        state = state_result.scalar_one_or_none()

        if state:
            await session.delete(state)

        return True

    async def _get_or_create_conversation(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID | None,
    ) -> tuple[Conversation, QueryAST | None]:
        """
        Get existing conversation or create new one.
        
        Args:
            session: Database session.
            user_id: The user's ID.
            conversation_id: Optional conversation ID to continue.
            
        Returns:
            Tuple of (conversation, previous_ast).
            
        Raises:
            PermissionError: If conversation_id is provided but doesn't exist
                           or doesn't belong to the user.
        """
        if conversation_id:
            # Fetch existing conversation
            result = await session.execute(
                select(Conversation)
                .where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()

            # Check if conversation exists
            if conversation is None:
                raise PermissionError(
                    f"Conversation {conversation_id} not found"
                )
            
            # Check if user owns the conversation
            if conversation.user_id != user_id:
                raise PermissionError(
                    "Not authorized to access this conversation"
                )

            # Load previous AST
            state_result = await session.execute(
                select(ConversationState).where(
                    ConversationState.conversation_id == conversation_id
                )
            )
            state = state_result.scalar_one_or_none()

            if state and state.ast_json:
                try:
                    previous_ast = QueryAST.model_validate(state.ast_json)
                    return conversation, previous_ast
                except Exception:
                    pass

            return conversation, None

        # Create new conversation
        conversation = Conversation(user_id=user_id)
        session.add(conversation)
        await session.flush()

        return conversation, None

    async def _save_conversation_state(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        ast: QueryAST,
    ) -> None:
        """Save AST to conversation state."""
        # Check if state exists
        result = await session.execute(
            select(ConversationState).where(
                ConversationState.conversation_id == conversation_id
            )
        )
        state = result.scalar_one_or_none()

        ast_dict = ast.model_dump(mode="json")

        if state:
            state.ast_json = ast_dict
        else:
            state = ConversationState(
                conversation_id=conversation_id,
                ast_json=ast_dict,
            )
            session.add(state)

    def _create_default_tables(self) -> dict:
        """Create default SQLAlchemy tables for the compiler."""
        from sqlalchemy import Column, Date, ForeignKey, Integer, MetaData, Numeric, String
        from sqlalchemy import Table as SATable
        from sqlalchemy.dialects.postgresql import UUID

        metadata = MetaData()

        orders = SATable(
            "orders",
            metadata,
            Column("order_id", UUID(as_uuid=True), primary_key=True),
            Column("customer_id", UUID(as_uuid=True), ForeignKey("customers.customer_id")),
            Column("product_id", UUID(as_uuid=True), ForeignKey("products.product_id")),
            Column("order_date", Date),
            Column("quantity", Integer),
            Column("unit_price", Numeric(10, 2)),
            Column("region", String),
        )

        products = SATable(
            "products",
            metadata,
            Column("product_id", UUID(as_uuid=True), primary_key=True),
            Column("product_line", String),
            Column("category", String),
        )

        customers = SATable(
            "customers",
            metadata,
            Column("customer_id", UUID(as_uuid=True), primary_key=True),
            Column("name", String),
            Column("segment", String),
            Column("country", String),
        )

        return {
            "orders": orders,
            "products": products,
            "customers": customers,
        }

    def _validate_ast(self, ast: QueryAST) -> str | None:
        """Validate AST and return error string if invalid."""
        try:
            self._validator.validate(ast)
        except ASTValidationError as e:
            return str(e)
        return None

    def _retry_parse_with_validation_feedback(
        self,
        query: str,
        validation_error: str,
    ) -> QueryAST | None:
        """
        Retry parsing once with validation feedback for the LLM.

        This nudges the model to correct semantic mistakes like
        non-aggregatable metrics or unknown fields.
        """
        retry_prompt = (
            f"{query}\n\n"
            "The previous QueryAST failed validation:\n"
            f"{validation_error}\n\n"
            "Please correct the QueryAST. Use only valid fields from the schema. "
            "Metrics must be aggregatable or derived, and date fields should "
            "be used as dimensions for trends."
        )

        try:
            return self._parser.parse(retry_prompt)
        except Exception:
            return None


# Global service instance
_nlq_service: NLQService | None = None


def get_nlq_service() -> NLQService:
    """Get the NLQ service instance."""
    global _nlq_service
    if _nlq_service is None:
        _nlq_service = NLQService()
    return _nlq_service
