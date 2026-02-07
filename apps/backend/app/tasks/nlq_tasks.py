"""Celery tasks for NLQ query processing."""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from uuid import UUID

from celery import Task as CeleryTask
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.models.conversation import Conversation
from app.models.conversation_state import ConversationState
from app.models.task import Task, TaskStatus, TaskType
from packages.core.conversation import IntentClassifier, QueryIntent, merge_ast
from packages.core.explainability import ExplainabilityBuilder
from packages.core.safety.validator import ASTValidationError, ASTValidator
from packages.core.schema_registry.registry import get_default_registry
from packages.core.sql_ast.compiler import SQLCompiler
from packages.core.sql_ast.join_resolver import JoinResolver
from packages.core.sql_ast.models import QueryAST
from packages.core.viz_inference import infer_visualization
from packages.llm.factory import LLMFactory
from packages.llm.parser import NLQParser

logger = logging.getLogger(__name__)
settings = get_settings()

# Create sync engine for Celery tasks (workers can't use async)
sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


class CallbackTask(CeleryTask):
    """Base task with database session and status tracking."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(f"Celery task {task_id} failed: {exc}")

        # Extract our Task model ID from kwargs
        our_task_id = kwargs.get("task_id")
        if not our_task_id:
            logger.debug(f"No task_id in kwargs for Celery task {task_id}")
            return

        # Update task status in database using our Task model ID
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(our_task_id)).first()
            if task:
                task.status = TaskStatus.FAILURE
                task.error_message = str(exc)
                task.completed_at = datetime.now(timezone.utc)
                session.commit()
            else:
                logger.error(f"Task {our_task_id} not found in database (on_failure)")

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(f"Celery task {task_id} completed successfully")

        # Extract our Task model ID from kwargs
        our_task_id = kwargs.get("task_id")
        if not our_task_id:
            logger.debug(f"No task_id in kwargs for Celery task {task_id}")
            return

        # Update task status in database using our Task model ID
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(our_task_id)).first()
            if task:
                task.status = TaskStatus.SUCCESS
                task.result = retval
                task.completed_at = datetime.now(timezone.utc)
                session.commit()
            else:
                logger.error(f"Task {our_task_id} not found in database (on_success)")

    def update_progress(self, task_id: str, current: int, total: int, message: str):
        """
        Update task progress in database.
        
        Args:
            task_id: Our Task model UUID (not Celery task ID).
            current: Current progress value.
            total: Total progress value.
            message: Progress message.
        """
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(task_id)).first()
            if task:
                task.status = TaskStatus.PROGRESS
                task.progress_current = current
                task.progress_total = total
                task.progress_message = message
                session.commit()
            else:
                logger.error(f"Task {task_id} not found in database (update_progress)")


def _create_default_tables():
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


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="app.tasks.nlq_tasks.process_nlq_query_task",
    soft_time_limit=120,
    time_limit=150,
    max_retries=0,
)
def process_nlq_query_task(
    self,
    task_id: str,
    query: str,
    user_id: str,
    tenant_id: str,
    conversation_id: str | None = None,
) -> dict:
    """
    Process an NLQ query in the background with progress updates.
    
    Args:
        task_id: Task UUID for progress tracking.
        query: User's natural language query.
        user_id: User UUID.
        tenant_id: Tenant UUID.
        conversation_id: Optional conversation UUID for context.
    
    Returns:
        Dict containing NLQResponse data.
    """
    logger.info(f"Starting NLQ query task {task_id} for user {user_id}")

    # Initialize components
    registry = get_default_registry()
    llm = LLMFactory.create_from_settings()
    parser = NLQParser(registry=registry, llm=llm)
    validator = ASTValidator(registry=registry)
    resolver = JoinResolver(registry=registry)
    classifier = IntentClassifier(llm=llm)
    explainability = ExplainabilityBuilder()
    
    tables = _create_default_tables()
    compiler = SQLCompiler(sqlalchemy_tables=tables, registry=registry)

    # Check for revocation
    if self.is_aborted():
        logger.info(f"Task {task_id} was revoked")
        return {}

    with SessionLocal() as session:
        # Step 1: Get or create conversation + load previous AST
        self.update_progress(task_id, 5, 100, "Loading conversation context...")
        
        previous_ast = None
        if conversation_id:
            result = session.execute(
                select(Conversation).where(Conversation.id == UUID(conversation_id))
            )
            conversation = result.scalar_one_or_none()
            
            if conversation and conversation.user_id == UUID(user_id):
                # Load previous AST
                state_result = session.execute(
                    select(ConversationState).where(
                        ConversationState.conversation_id == UUID(conversation_id)
                    )
                )
                state = state_result.scalar_one_or_none()
                
                if state and state.ast_json:
                    try:
                        previous_ast = QueryAST.model_validate(state.ast_json)
                    except Exception as e:
                        logger.warning(f"Failed to load previous AST: {e}")
        else:
            # Create new conversation
            conversation = Conversation(user_id=UUID(user_id))
            session.add(conversation)
            session.flush()
            conversation_id = str(conversation.id)

        # Check for revocation
        if self.is_aborted():
            logger.info(f"Task {task_id} was revoked")
            return {}

        # Step 2: Intent classification and parsing (parallel if previous_ast exists)
        intent = QueryIntent.RESET
        parsed_ast = None
        
        if previous_ast is not None:
            # Parallel execution
            self.update_progress(task_id, 10, 100, "Classifying intent and parsing query...")
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                try:
                    intent_future = executor.submit(classifier.classify, query, previous_ast)
                    parse_future = executor.submit(parser.parse, query)
                    
                    intent = intent_future.result(timeout=60)
                    parsed_ast = parse_future.result(timeout=60)
                except FuturesTimeoutError as e:
                    raise Exception(f"LLM call timed out: {e}")
        else:
            # No previous context, just parse
            self.update_progress(task_id, 30, 100, "Parsing query with AI...")
            parsed_ast = parser.parse(query)

        # Check for revocation
        if self.is_aborted():
            logger.info(f"Task {task_id} was revoked")
            return {}

        # Step 3: Merge if REFINE
        self.update_progress(task_id, 50, 100, "Validating query...")
        
        merged = False
        final_ast = parsed_ast
        
        if intent == QueryIntent.REFINE and previous_ast is not None:
            try:
                final_ast = merge_ast(previous_ast, parsed_ast)
                merged = True
            except Exception as e:
                logger.warning(f"Failed to merge AST: {e}")
                final_ast = parsed_ast
                merged = False

        # Step 4: Validate AST
        validation_error = None
        try:
            validator.validate(final_ast)
        except ASTValidationError as e:
            validation_error = str(e)
            
            # Try fallback to parsed AST if merge caused issues
            if merged:
                try:
                    validator.validate(parsed_ast)
                    final_ast = parsed_ast
                    merged = False
                    validation_error = None
                except ASTValidationError:
                    pass

        # Step 5: Retry parsing once with validation feedback if still invalid
        if validation_error:
            self.update_progress(task_id, 60, 100, "Retrying with validation feedback...")
            
            # Check for revocation
            if self.is_aborted():
                logger.info(f"Task {task_id} was revoked")
                return {}
            
            retry_prompt = (
                f"{query}\n\n"
                "The previous QueryAST failed validation:\n"
                f"{validation_error}\n\n"
                "Please correct the QueryAST. Use only valid fields from the schema. "
                "Metrics must be aggregatable or derived, and date fields should "
                "be used as dimensions for trends."
            )
            
            try:
                retry_ast = parser.parse(retry_prompt)
                validator.validate(retry_ast)
                final_ast = retry_ast
                merged = False
                validation_error = None
            except Exception:
                pass

        if validation_error:
            raise Exception(f"Validation error: {validation_error}")

        # Check for revocation
        if self.is_aborted():
            logger.info(f"Task {task_id} was revoked")
            return {}

        # Step 6: Resolve joins
        self.update_progress(task_id, 70, 100, "Resolving joins...")
        join_plan = resolver.resolve(final_ast)

        # Step 7: Compile SQL
        self.update_progress(task_id, 80, 100, "Compiling SQL...")
        statement = compiler.compile(final_ast, join_plan)
        
        # Get SQL string
        sql_string = str(statement.compile(compile_kwargs={"literal_binds": True}))

        # Step 8: Execute query
        self.update_progress(task_id, 90, 100, "Executing query...")
        
        from sqlalchemy import text
        result = session.execute(text(sql_string))
        columns = list(result.keys())
        rows = [list(row) for row in result.fetchall()]

        # Step 9: Build explainability
        explanation = explainability.build(final_ast, join_plan)

        # Step 10: Infer visualization
        visualization = infer_visualization(final_ast, registry)

        # Step 11: Save conversation state
        state_result = session.execute(
            select(ConversationState).where(
                ConversationState.conversation_id == UUID(conversation_id)
            )
        )
        state = state_result.scalar_one_or_none()
        
        ast_dict = final_ast.model_dump(mode="json")
        
        if state:
            state.ast_json = ast_dict
        else:
            state = ConversationState(
                conversation_id=UUID(conversation_id),
                ast_json=ast_dict,
            )
            session.add(state)
        
        session.commit()

        # Step 12: Build result
        self.update_progress(task_id, 100, 100, "Complete!")
        
        result_dict = {
            "conversation_id": conversation_id,
            "ast": {
                "metrics": [
                    {
                        "function": m.function.value,
                        "field": m.field,
                        "alias": m.alias,
                    }
                    for m in final_ast.metrics
                ],
                "dimensions": [
                    {"field": d.field, "alias": d.alias}
                    for d in final_ast.dimensions
                ],
                "filters": [
                    {
                        "field": f.field,
                        "operator": f.operator.value,
                        "value": f.value,
                    }
                    for f in final_ast.filters
                ],
                "order_by": [
                    {"field": o.field, "direction": o.direction.value}
                    for o in final_ast.order_by
                ],
                "limit": final_ast.limit,
            },
            "explainability": explanation.to_dict(),
            "visualization": visualization.to_dict(),
            "sql": sql_string,
            "columns": columns,
            "rows": rows,
            "intent": intent.value if intent else None,
            "merged": merged,
        }
        
        logger.info(f"NLQ query task {task_id} completed successfully")
        return result_dict
