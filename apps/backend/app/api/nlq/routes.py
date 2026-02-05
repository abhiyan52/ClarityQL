"""NLQ API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import AsyncSessionDep, CurrentUser
from app.schemas.nlq import (
    ASTSchema,
    DimensionSchema,
    ExplainabilitySchema,
    FilterSchema,
    MetricSchema,
    NLQQueryRequest,
    NLQQueryResponse,
    NLQResetResponse,
    OrderBySchema,
    VisualizationSchema,
)
from app.services.analytics_nlq.service import get_nlq_service

router = APIRouter()


@router.post("/query", response_model=NLQQueryResponse)
async def submit_nlq_query(
    payload: NLQQueryRequest,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> NLQQueryResponse:
    """
    Process a natural language analytics query.

    This endpoint accepts a natural language query, converts it to SQL,
    executes it, and returns the results with explainability.

    Supports conversational context - provide conversation_id to refine
    a previous query.

    Args:
        payload: The query request with optional conversation_id.
        current_user: Authenticated user (from JWT).
        session: Database session.

    Returns:
        Query results with AST, SQL, and explainability.

    Raises:
        HTTPException 400: If query processing fails.
        HTTPException 401: If not authenticated.
        HTTPException 403: If conversation belongs to another user.
    """
    service = get_nlq_service()

    try:
        result = await service.process_query(
            query=payload.query,
            user_id=current_user.id,
            session=session,
            conversation_id=payload.conversation_id,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation",
        )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": result.error,
                "error_type": result.error_type,
                "conversation_id": str(result.conversation_id),
            },
        )

    # Convert AST to schema
    ast_schema = ASTSchema(
        metrics=[
            MetricSchema(
                function=m.function.value,
                field=m.field,
                alias=m.alias,
            )
            for m in result.ast.metrics
        ],
        dimensions=[
            DimensionSchema(field=d.field, alias=d.alias)
            for d in result.ast.dimensions
        ],
        filters=[
            FilterSchema(
                field=f.field,
                operator=f.operator.value,
                value=f.value,
            )
            for f in result.ast.filters
        ],
        order_by=[
            OrderBySchema(field=o.field, direction=o.direction.value)
            for o in result.ast.order_by
        ],
        limit=result.ast.limit,
    )

    # Convert explainability to schema
    explain_schema = ExplainabilitySchema(
        aggregates=result.explainability.get("aggregates", []),
        group_by=result.explainability.get("groupBy", []),
        filters=result.explainability.get("filters", []),
        order_by=result.explainability.get("orderBy", []),
        limit=result.explainability.get("limit"),
        source_tables=result.explainability.get("sourceTables", []),
    )

    # Convert visualization to schema
    viz_dict = result.visualization.to_dict()
    viz_schema = VisualizationSchema(
        type=viz_dict["type"],
        x=viz_dict["x"],
        y=viz_dict["y"],
        series=viz_dict["series"],
    )

    return NLQQueryResponse(
        conversation_id=result.conversation_id,
        ast=ast_schema,
        explainability=explain_schema,
        visualization=viz_schema,
        sql=result.sql,
        columns=result.execution_result.columns,
        rows=result.execution_result.rows,
        intent=result.intent.value if result.intent else None,
        merged=result.merged,
    )


@router.post("/reset/{conversation_id}", response_model=NLQResetResponse)
async def reset_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> NLQResetResponse:
    """
    Reset a conversation's context.

    Clears the stored AST so the next query starts fresh.

    Args:
        conversation_id: The conversation to reset.
        current_user: Authenticated user (from JWT).
        session: Database session.

    Returns:
        Confirmation message.

    Raises:
        HTTPException 403: If conversation belongs to another user.
        HTTPException 404: If conversation not found.
    """
    service = get_nlq_service()

    try:
        success = await service.reset_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            session=session,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return NLQResetResponse(conversation_id=conversation_id)
