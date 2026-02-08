"""RAG ingestion API routes with async task support."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.dependencies import AsyncSessionDep, CurrentUser
from app.db.session import async_session_factory
from app.models.task import Task, TaskStatus, TaskType
from app.tasks.rag_tasks import (
    ingest_document_task,
    generate_embeddings_task,
    generate_embeddings_batch_task,
    generate_embeddings_for_pending_documents_task,
    process_rag_query_task,
)
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageRole
from app.services.rag.query_service import RAGQueryService
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import selectinload

router = APIRouter()
logger = logging.getLogger(__name__)

# Directory for uploaded files (configure via settings in production)
UPLOAD_DIR = Path("/tmp/clarityql_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _extract_original_filename(storage_path: str | None) -> str | None:
    """
    Extract the original filename from storage path.
    
    Storage path format: {user_id}_{original_filename}
    Example: /tmp/clarityql_uploads/550e8400-e29b-41d4-a716-446655440000_report.pdf
    Returns: report.pdf
    """
    if not storage_path:
        return None
    # Get the basename (filename part)
    basename = storage_path.split("/")[-1]
    # Remove the user_id prefix (UUID followed by underscore)
    # UUID format: 8-4-4-4-12 hex characters (but be flexible with last segment)
    import re
    match = re.match(r'^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]+)_(.+)', basename, re.IGNORECASE)
    if match:
        return match.group(2)
    return basename


# ──────────────────────────────────────────────
# Request/Response Schemas
# ──────────────────────────────────────────────


class RAGQueryRequest(BaseModel):
    """Request schema for RAG query."""

    query: str = Field(..., min_length=1, max_length=5000, description="User query")
    document_ids: list[str] | None = Field(
        None, description="Optional list of document IDs to search (None = all)"
    )
    conversation_id: str | None = Field(
        None, description="Optional conversation ID for context"
    )
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    min_similarity: float = Field(
        0.0, ge=0.0, le=1.0, description="Minimum similarity threshold"
    )


class ChunkResult(BaseModel):
    """A single chunk result from RAG query."""

    chunk_id: str
    document_id: str
    document_title: str
    content: str
    page_number: int | None
    section: str | None
    chunk_index: int
    similarity_score: float
    token_count: int | None


class RAGQueryResponse(BaseModel):
    """Response schema for RAG query."""

    conversation_id: str
    query: str
    answer: str
    chunks: list[ChunkResult]
    documents: list[dict]
    total_chunks_found: int


# ──────────────────────────────────────────────
# RAG Query Endpoint
# ──────────────────────────────────────────────


@router.get("/conversations")
async def list_rag_conversations(
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> list[dict]:
    """List all RAG conversations for the current user."""
    result = await session.execute(
        select(Conversation)
        .where(
            Conversation.user_id == current_user.id,
            Conversation.conversation_type == "rag"
        )
        .order_by(desc(Conversation.updated_at))
    )
    conversations = result.scalars().all()
    
    return [
        {
            "id": str(c.id),
            "title": c.title or "New Document Chat",
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "status": c.status.value,
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}")
async def get_rag_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> dict:
    """Get RAG conversation details and messages."""
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.conversation_type == "rag"
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
        
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation",
        )
        
    return {
        "id": str(conversation.id),
        "title": conversation.title or "New Document Chat",
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "status": conversation.status.value,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "meta": m.meta,
            }
            for m in conversation.messages
        ]
    }


@router.delete("/conversations/{conversation_id}")
async def delete_rag_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> dict:
    """Delete a RAG conversation."""
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.conversation_type == "rag"
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
        
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this conversation",
        )
        
    await session.delete(conversation)
    await session.commit()
    
    return {"message": "Conversation deleted successfully"}


@router.post("/query", status_code=status.HTTP_202_ACCEPTED)
async def query_documents(
    request: RAGQueryRequest,
    session: AsyncSessionDep,
    current_user: CurrentUser,
) -> dict:
    """
    Submit a RAG query for background processing.
    """
    try:
        # Validate document IDs if provided
        document_ids = None
        if request.document_ids:
            try:
                for doc_id in request.document_ids:
                    UUID(doc_id)
                document_ids = request.document_ids
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid document ID format: {str(e)}",
                )

        # Handle conversation
        conversation_id = None
        if request.conversation_id:
            try:
                conv_uuid = UUID(request.conversation_id)
                result = await session.execute(
                    select(Conversation).where(Conversation.id == conv_uuid)
                )
                conversation = result.scalar_one_or_none()
                if not conversation:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Conversation not found",
                    )
                conversation_id = str(conversation.id)
                # Update status
                conversation.status = ConversationStatus.ACTIVE
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid conversation ID format",
                )
        else:
            # Create new RAG conversation
            conversation = Conversation(
                user_id=current_user.id,
                conversation_type="rag",
                title=f"Chat: {request.query[:30]}...",
                status=ConversationStatus.ACTIVE
            )
            session.add(conversation)
            await session.flush()
            conversation_id = str(conversation.id)

        # Create task record
        task = Task(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            task_type=TaskType.RAG_QUERY,
            task_name=f"RAG Query: {request.query[:50]}...",
            task_args={
                "query": request.query,
                "document_ids": document_ids,
                "conversation_id": conversation_id,
                "top_k": request.top_k,
                "min_similarity": request.min_similarity,
            },
            status=TaskStatus.PENDING,
            progress_current=0,
            progress_total=100,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

        # Dispatch Celery task
        celery_result = process_rag_query_task.apply_async(
            kwargs={
                "task_id": str(task.id),
                "query": request.query,
                "user_id": str(current_user.id),
                "tenant_id": str(current_user.tenant_id),
                "document_ids": document_ids,
                "conversation_id": conversation_id,
                "top_k": request.top_k,
                "min_similarity": request.min_similarity,
            }
        )

        # Update task with Celery task ID
        task.celery_task_id = celery_result.id
        task.started_at = datetime.utcnow()
        await session.commit()

        return {
            "task_id": str(task.id),
            "conversation_id": conversation_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query submission failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query submission failed: {str(e)}",
        )


# ──────────────────────────────────────────────
# RAG Query Task Streaming and Cancellation
# ──────────────────────────────────────────────


@router.get("/tasks/{task_id}/stream")
async def stream_rag_task_status(
    task_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
):
    """
    Stream RAG task progress and results via Server-Sent Events (SSE).

    Opens an SSE connection that emits progress updates and the final result.

    Event types:
    - progress: { percentage, message, current, total }
    - complete: { full RAGQueryResponse data }
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
        last_progress = None

        while True:
            # IMPORTANT: create a fresh session each poll so we see
            # the latest data committed by the Celery worker.
            async with async_session_factory() as poll_session:
                result = await poll_session.execute(
                    select(Task).where(Task.id == task_id)
                )
                current_task = result.scalar_one_or_none()
                
                if not current_task:
                    data = {"error": "Task not found", "error_type": "task_deleted"}
                    yield f"event: error\ndata: {json.dumps(data)}\n\n"
                    return

                task_status = current_task.status

                if task_status == TaskStatus.PROGRESS:
                    current_progress = (current_task.progress_current, current_task.progress_message)
                    if current_progress != last_progress:
                        data = {
                            "percentage": current_task.progress_percentage,
                            "message": current_task.progress_message or "",
                            "current": current_task.progress_current,
                            "total": current_task.progress_total,
                        }
                        yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                        last_progress = current_progress

                elif task_status == TaskStatus.SUCCESS:
                    yield f"event: complete\ndata: {json.dumps(current_task.result)}\n\n"
                    return

                elif task_status == TaskStatus.FAILURE:
                    data = {
                        "error": current_task.error_message or "Unknown error",
                        "error_type": "task_failure",
                    }
                    yield f"event: error\ndata: {json.dumps(data)}\n\n"
                    return

                elif task_status == TaskStatus.REVOKED:
                    data = {"message": "Task was cancelled"}
                    yield f"event: cancelled\ndata: {json.dumps(data)}\n\n"
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
async def cancel_rag_task(
    task_id: UUID,
    current_user: CurrentUser,
    session: AsyncSessionDep,
) -> dict:
    """
    Cancel a running RAG task.

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


# ──────────────────────────────────────────────
# Document Ingestion Endpoints
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# Document Ingestion Endpoints
# ──────────────────────────────────────────────


@router.post("/ingest")
async def ingest_document_async(
    file: UploadFile = File(...),
    document_title: str | None = None,
    description: str | None = None,
    language: str | None = None,
    max_chunk_tokens: int = 500,
    chunk_overlap_tokens: int = 50,
    session: AsyncSessionDep = None,
    current_user: CurrentUser = None,
) -> JSONResponse:
    """
    Ingest a document asynchronously (background task).

    Returns immediately with a task ID that can be used to track progress.

    Args:
        file: Uploaded document file.
        document_title: Optional title (defaults to filename).
        description: Optional document description.
        language: Optional language override (auto-detected if not provided).
        max_chunk_tokens: Maximum tokens per chunk (default: 500).
        chunk_overlap_tokens: Overlap between chunks (default: 50).
        session: Database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        JSON with task_id for tracking.

    Raises:
        HTTPException 400: If file validation fails.
        HTTPException 500: If task creation fails.

    Example:
        ```bash
        curl -X POST http://localhost:8000/api/rag/ingest \\
          -F "file=@report.pdf" \\
          -F "document_title=Q4 Report" \\
          -H "Authorization: Bearer <token>"

        # Response:
        {
          "task_id": "550e8400-e29b-41d4-a716-446655440000",
          "status": "PENDING",
          "message": "Document upload successful. Processing in background.",
          "status_url": "/api/rag/tasks/550e8400-..."
        }
        ```
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided",
            )

        # Save uploaded file
        file_path = UPLOAD_DIR / f"{current_user.id}_{file.filename}"

        try:
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            logger.info(
                f"File uploaded: {file.filename} "
                f"({len(content)} bytes) by user {current_user.id}"
            )

        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}",
            )

        # Check for duplicate document by checksum
        import hashlib
        from app.models.document import Document as DocumentModel
        
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk_data in iter(lambda: f.read(4096), b""):
                sha256.update(chunk_data)
        checksum = sha256.hexdigest()
        
        # Check if document already exists
        from sqlalchemy import select
        result = await session.execute(
            select(DocumentModel).where(
                DocumentModel.tenant_id == current_user.tenant_id,
                DocumentModel.checksum == checksum,
            )
        )
        existing_doc = result.scalar_one_or_none()
        
        if existing_doc:
            logger.info(
                f"Duplicate document detected (checksum={checksum}), will reprocess: {existing_doc.id}"
            )
            message = f"Document already exists. Reprocessing with new settings."
        else:
            message = "Document upload successful. Processing in background."

        # Create task record in database first (before queueing Celery task)
        # This prevents race conditions where the worker starts before the DB commit
        task = Task(
            task_type=TaskType.DOCUMENT_INGESTION,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            status=TaskStatus.PENDING,
            task_name=f"Ingest document: {document_title or file.filename}",
            task_args={
                "file_name": file.filename,
                "document_title": document_title,
                "max_chunk_tokens": max_chunk_tokens,
            },
            celery_task_id=None,  # Will be set after queueing
        )

        session.add(task)
        await session.flush()  # Get task.id
        await session.refresh(task)

        # Use Task ID as Celery task ID to avoid races updating celery_task_id
        task.celery_task_id = str(task.id)
        
        # ⚠️ EXCEPTIONAL CASE: Commit before queuing Celery task
        # Normally we let the session dependency handle commits, but here we MUST
        # commit before queuing because:
        # 1. The Celery worker runs in a separate process/transaction
        # 2. It needs to see the Task record immediately when it starts
        # 3. Without commit, worker's transaction won't see this uncommitted record
        # 4. This violates our usual "no manual commits" rule, but it's necessary
        #    for background task coordination
        await session.commit()

        # Queue Celery task with Task ID as Celery task ID
        celery_task = ingest_document_task.apply_async(
            kwargs={
                "file_path": str(file_path),
                "document_title": document_title,
                "description": description,
                "language": language,
                "tenant_id": str(current_user.tenant_id),
                "owner_user_id": str(current_user.id),
                "max_chunk_tokens": max_chunk_tokens,
                "chunk_overlap_tokens": chunk_overlap_tokens,
            },
            task_id=str(task.id),
        )

        logger.info(
            f"Ingestion task queued: {task.id} (Celery: {celery_task.id})"
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "task_id": str(task.id),
                "celery_task_id": celery_task.id,
                "status": task.status.value,
                "message": message,
                "is_reprocessing": existing_doc is not None,
                "existing_document_id": str(existing_doc.id) if existing_doc else None,
                "status_url": f"/api/rag/tasks/{task.id}",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}",
        )


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    session: AsyncSessionDep,
    current_user: CurrentUser,
) -> JSONResponse:
    """
    Get status of an ingestion task.

    Args:
        task_id: UUID of the task.
        session: Database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        JSON with task status and progress.

    Raises:
        HTTPException 404: If task not found or not accessible.

    Example:
        ```bash
        curl http://localhost:8000/api/rag/tasks/550e8400-... \\
          -H "Authorization: Bearer <token>"

        # Response:
        {
          "task_id": "550e8400-...",
          "status": "PROGRESS",
          "progress": 75.0,
          "progress_message": "Creating chunks...",
          "created_at": "2024-02-06T14:30:00Z",
          "started_at": "2024-02-06T14:30:05Z",
          "completed_at": null,
          "result": null,
          "error_message": null
        }
        ```
    """
    from sqlalchemy import select

    # Parse UUID
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID format",
        )

    # Fetch task (verify access)
    result = await session.execute(
        select(Task).where(
            Task.id == task_uuid,
            Task.tenant_id == current_user.tenant_id,
        )
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or not accessible",
        )

    return JSONResponse(
        content={
            "task_id": str(task.id),
            "celery_task_id": task.celery_task_id,
            "task_type": task.task_type.value,
            "task_name": task.task_name,
            "status": task.status.value,
            "progress": task.progress_percentage,
            "progress_message": task.progress_message,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "duration_seconds": task.duration_seconds,
            "result": task.result,
            "error_message": task.error_message,
        }
    )


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    session: AsyncSessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
) -> JSONResponse:
    """Get chunks for a specific document."""
    from sqlalchemy import select
    from app.models.document import Document
    from app.models.chunk import Chunk

    # Parse UUID
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format",
        )

    # Fetch document (verify access)
    result = await session.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )

    # Fetch chunks with pagination
    offset = (page - 1) * page_size

    result = await session.execute(
        select(Chunk)
        .where(Chunk.document_id == doc_uuid)
        .order_by(Chunk.chunk_index)
        .limit(page_size)
        .offset(offset)
    )
    chunks = result.scalars().all()

    return JSONResponse(
        content={
            "document_id": str(document.id),
            "document_title": document.title,
            "total_chunks": document.chunk_count,
            "page": page,
            "page_size": page_size,
            "chunks": [
                {
                    "id": str(chunk.id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_count": chunk.token_count,
                    "page_number": chunk.page_number,
                    "section": chunk.section,
                    "language": chunk.language,
                    "has_embedding": chunk.embedding is not None,
                }
                for chunk in chunks
            ],
        }
    )


@router.get("/documents")
async def list_documents(
    session: AsyncSessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> JSONResponse:
    """List documents for the current user's tenant."""
    from sqlalchemy import select, func
    from app.models.document import Document

    # Count total documents
    count_result = await session.execute(
        select(func.count(Document.id)).where(
            Document.tenant_id == current_user.tenant_id,
            Document.is_active == True,
        )
    )
    total = count_result.scalar()

    # Fetch documents
    offset = (page - 1) * page_size

    result = await session.execute(
        select(Document)
        .where(
            Document.tenant_id == current_user.tenant_id,
            Document.is_active == True,
        )
        .order_by(Document.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    documents = result.scalars().all()

    return JSONResponse(
        content={
            "total": total,
            "page": page,
            "page_size": page_size,
            "documents": [
                {
                    "id": str(doc.id),
                    "title": doc.title,
                    "file_name": _extract_original_filename(doc.storage_path),
                    "description": doc.description,
                    "language": doc.language,
                    "chunk_count": doc.chunk_count,
                    "source_type": doc.source_type.value,
                    "visibility": doc.visibility.value,
                    "processing_status": doc.processing_status.value,
                    "processing_error": doc.processing_error,
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat(),
                }
                for doc in documents
            ],
        }
    )


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    session: AsyncSessionDep,
    current_user: CurrentUser,
) -> JSONResponse:
    """Get a specific document with full details including processing status."""
    from sqlalchemy import select
    from app.models.document import Document

    # Parse UUID
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format",
        )

    # Fetch document (verify access)
    result = await session.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )

    return JSONResponse(
        content={
            "id": str(document.id),
            "title": document.title,
            "file_name": _extract_original_filename(document.storage_path),
            "description": document.description,
            "language": document.language,
            "chunk_count": document.chunk_count,
            "source_type": document.source_type.value,
            "visibility": document.visibility.value,
            "processing_status": document.processing_status.value,
            "processing_error": document.processing_error,
            "file_size_bytes": document.file_size_bytes,
            "mime_type": document.mime_type,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat(),
        }
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    session: AsyncSessionDep,
    current_user: CurrentUser,
):
    """Download the original document file."""
    from sqlalchemy import select
    from app.models.document import Document
    from fastapi.responses import FileResponse
    import os

    # Parse UUID
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format",
        )

    # Fetch document (verify access)
    result = await session.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )

    # Check if file exists
    if not document.storage_path or not os.path.exists(document.storage_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on server",
        )

    # Return file
    return FileResponse(
        path=document.storage_path,
        filename=document.title,
        media_type=document.mime_type or "application/octet-stream",
    )


@router.post("/documents/{document_id}/generate-embeddings")
async def generate_embeddings_for_document(
    document_id: str,
    session: AsyncSessionDep,
    current_user: CurrentUser,
    force: bool = False,
) -> JSONResponse:
    """
    Trigger embedding generation for a specific document.

    This endpoint allows manual triggering of embedding generation for:
    - Documents that failed embedding generation
    - Documents in CHUNKED status (not yet embedded)
    - Documents in READY status (with force=true to regenerate)

    Args:
        document_id: UUID of the document.
        session: Database session (injected).
        current_user: Authenticated user (injected).
        force: If true, regenerate embeddings even if document is READY.

    Returns:
        JSON with task status.

    Raises:
        HTTPException 404: If document not found.
        HTTPException 400: If document status is invalid for embedding.

    Example:
        ```bash
        curl -X POST http://localhost:8000/api/rag/documents/550e8400-.../generate-embeddings \\
          -H "Authorization: Bearer <token>"

        # Force regeneration:
        curl -X POST "http://localhost:8000/api/rag/documents/550e8400-.../generate-embeddings?force=true" \\
          -H "Authorization: Bearer <token>"
        ```
    """
    from sqlalchemy import select
    from app.models.document import Document, DocumentProcessingStatus

    # Parse UUID
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format",
        )

    # Fetch document (verify access)
    result = await session.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )

    # Check if document has chunks
    if document.chunk_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no chunks to embed",
        )

    # Check document status
    valid_statuses = [
        DocumentProcessingStatus.CHUNKED,
        DocumentProcessingStatus.FAILED,
    ]

    if force:
        valid_statuses.append(DocumentProcessingStatus.READY)

    if document.processing_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot generate embeddings for document with status {document.processing_status.value}. "
                f"Use force=true to regenerate embeddings for READY documents."
            ),
        )

    # If forcing regeneration, clear existing embeddings
    if force and document.processing_status == DocumentProcessingStatus.READY:
        from app.models.chunk import Chunk
        from sqlalchemy import update

        logger.info(f"Force regeneration: clearing embeddings for document {document_id}")

        await session.execute(
            update(Chunk)
            .where(Chunk.document_id == doc_uuid)
            .values(embedding=None)
        )

        # Set status back to CHUNKED
        document.processing_status = DocumentProcessingStatus.CHUNKED
        await session.commit()

    # Queue embedding task
    try:
        celery_task = generate_embeddings_task.delay(document_id=str(doc_uuid))

        logger.info(
            f"Embedding generation queued for document {document_id}: {celery_task.id}"
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "document_id": str(doc_uuid),
                "celery_task_id": celery_task.id,
                "status": "queued",
                "message": "Embedding generation queued successfully",
            },
        )

    except Exception as e:
        logger.error(f"Failed to queue embedding task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue embedding task: {str(e)}",
        )


@router.post("/embeddings/generate-batch")
async def generate_embeddings_batch(
    document_ids: list[str] = Body(...),
    session: AsyncSessionDep = None,
    current_user: CurrentUser = None,
) -> JSONResponse:
    """
    Generate embeddings for multiple documents in parallel.

    This endpoint allows batch processing of embeddings for multiple documents.

    Args:
        document_ids: List of document UUIDs.
        session: Database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        JSON with batch task status.

    Raises:
        HTTPException 400: If document IDs are invalid.

    Example:
        ```bash
        curl -X POST http://localhost:8000/api/rag/embeddings/generate-batch \\
          -H "Authorization: Bearer <token>" \\
          -H "Content-Type: application/json" \\
          -d '{"document_ids": ["550e8400-...", "660e8400-..."]}'
        ```
    """
    from sqlalchemy import select
    from app.models.document import Document

    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No document IDs provided",
        )

    # Validate document IDs and access
    valid_doc_ids = []

    for doc_id in document_ids:
        try:
            doc_uuid = UUID(doc_id)
        except ValueError:
            logger.warning(f"Invalid document ID format: {doc_id}")
            continue

        # Check document exists and user has access
        result = await session.execute(
            select(Document).where(
                Document.id == doc_uuid,
                Document.tenant_id == current_user.tenant_id,
            )
        )
        document = result.scalar_one_or_none()

        if document and document.chunk_count > 0:
            valid_doc_ids.append(doc_id)
        else:
            logger.warning(f"Document {doc_id} not found or has no chunks")

    if not valid_doc_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid documents found for embedding generation",
        )

    # Queue batch embedding task
    try:
        celery_task = generate_embeddings_batch_task.delay(
            document_ids=valid_doc_ids,
            batch_size=32,
        )

        logger.info(
            f"Batch embedding generation queued for {len(valid_doc_ids)} documents: {celery_task.id}"
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "documents_queued": len(valid_doc_ids),
                "celery_task_id": celery_task.id,
                "status": "queued",
                "message": f"Batch embedding generation queued for {len(valid_doc_ids)} documents",
            },
        )

    except Exception as e:
        logger.error(f"Failed to queue batch embedding task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue batch embedding task: {str(e)}",
        )


@router.post("/embeddings/generate-pending")
async def generate_embeddings_for_pending(
    session: AsyncSessionDep,
    current_user: CurrentUser,
) -> JSONResponse:
    """
    Generate embeddings for all pending documents (CHUNKED status).

    This is a maintenance endpoint that processes all documents waiting for embeddings.
    Useful for:
    - Recovering from failed embedding tasks
    - Processing backlog of documents
    - Scheduled maintenance jobs

    Args:
        session: Database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        JSON with task status.

    Example:
        ```bash
        curl -X POST http://localhost:8000/api/rag/embeddings/generate-pending \\
          -H "Authorization: Bearer <token>"
        ```
    """
    try:
        celery_task = generate_embeddings_for_pending_documents_task.delay()

        logger.info(f"Pending embeddings task queued: {celery_task.id}")

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "celery_task_id": celery_task.id,
                "status": "queued",
                "message": "Pending documents embedding generation queued successfully",
            },
        )

    except Exception as e:
        logger.error(f"Failed to queue pending embeddings task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue task: {str(e)}",
        )
