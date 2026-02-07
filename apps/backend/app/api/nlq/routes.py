"""NLQ API routes."""

import asyncio
import json
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.dependencies import AsyncSessionDep, CurrentUser
from app.models.task import Task, TaskStatus, TaskType
from app.schemas.nlq import (
    NLQQueryRequest,
    NLQResetResponse,
)
from app.services.analytics_nlq.service import get_nlq_service

router = APIRouter()


@router.post("/query", status_code=status.HTTP_202_ACCEPTED)
async def submit_nlq_query(
    payload: NLQQueryRequest,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> dict:
    """
    Submit a natural language analytics query for background processing.

    This endpoint creates a task and returns immediately with a task_id.
    The client should then connect to /tasks/{task_id}/stream to receive
    progress updates and final results via Server-Sent Events (SSE).

    Args:
        payload: The query request with optional conversation_id.
        current_user: Authenticated user (from JWT).
        session: Database session.

    Returns:
        Dict with task_id for progress tracking.

    Raises:
        HTTPException 401: If not authenticated.
    """
    # Create task record
    task = Task(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        task_type=TaskType.NLQ_QUERY,
        task_name=f"NLQ Query: {payload.query[:50]}...",
        task_args={
            "query": payload.query,
            "conversation_id": str(payload.conversation_id) if payload.conversation_id else None,
        },
        status=TaskStatus.PENDING,
        progress_current=0,
        progress_total=100,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # Dispatch Celery task
    from app.tasks.nlq_tasks import process_nlq_query_task
    
    celery_result = process_nlq_query_task.apply_async(
        kwargs={
            "task_id": str(task.id),
            "query": payload.query,
            "user_id": str(current_user.id),
            "tenant_id": str(current_user.tenant_id),
            "conversation_id": str(payload.conversation_id) if payload.conversation_id else None,
        }
    )

    # Update task with Celery task ID
    task.celery_task_id = celery_result.id
    task.started_at = datetime.utcnow()
    await session.commit()

    return {"task_id": str(task.id)}


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(
    task_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
):
    """
    Stream task progress and results via Server-Sent Events (SSE).

    Opens an SSE connection that emits progress updates and the final result.

    Event types:
    - progress: { percentage, message, step }
    - complete: { full NLQResponse data }
    - error: { error, error_type }
    - cancelled: { message }

    Args:
        task_id: The task UUID to stream.
        current_user: Authenticated user (from JWT).
        session: Database session.

    Returns:
        StreamingResponse with text/event-stream content type.

    Raises:
        HTTPException 403: If task belongs to another user.
        HTTPException 404: If task not found.
    """
    # Verify task exists and user owns it
    result = await session.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this task",
        )

    async def event_generator():
        """Generate SSE events from task status."""
        last_status = None
        last_progress = None

        while True:
            # Refresh task from DB
            await session.refresh(task)

            # Send progress event if status/progress changed
            if task.status == TaskStatus.PROGRESS:
                current_progress = (task.progress_current, task.progress_message)
                if current_progress != last_progress:
                    data = {
                        "percentage": task.progress_percentage,
                        "message": task.progress_message or "",
                        "current": task.progress_current,
                        "total": task.progress_total,
                    }
                    yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                    last_progress = current_progress

            # Send complete event
            elif task.status == TaskStatus.SUCCESS:
                if last_status != TaskStatus.SUCCESS:
                    yield f"event: complete\ndata: {json.dumps(task.result)}\n\n"
                    last_status = TaskStatus.SUCCESS
                return

            # Send error event
            elif task.status == TaskStatus.FAILURE:
                if last_status != TaskStatus.FAILURE:
                    data = {
                        "error": task.error_message or "Unknown error",
                        "error_type": "task_failure",
                    }
                    yield f"event: error\ndata: {json.dumps(data)}\n\n"
                    last_status = TaskStatus.FAILURE
                return

            # Send cancelled event
            elif task.status == TaskStatus.REVOKED:
                if last_status != TaskStatus.REVOKED:
                    data = {"message": "Task was cancelled"}
                    yield f"event: cancelled\ndata: {json.dumps(data)}\n\n"
                    last_status = TaskStatus.REVOKED
                return

            # Wait before next poll
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> dict:
    """
    Cancel a running NLQ task.

    Revokes the Celery task and marks it as REVOKED in the database.

    Args:
        task_id: The task UUID to cancel.
        current_user: Authenticated user (from JWT).
        session: Database session.

    Returns:
        Confirmation message.

    Raises:
        HTTPException 403: If task belongs to another user.
        HTTPException 404: If task not found.
    """
    # Verify task exists and user owns it
    result = await session.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this task",
        )

    # Revoke Celery task
    if task.celery_task_id:
        celery_app.control.revoke(task.celery_task_id, terminate=True)

    # Update task status
    task.status = TaskStatus.REVOKED
    task.completed_at = datetime.utcnow()
    await session.commit()

    return {"message": "Task cancelled successfully"}


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
