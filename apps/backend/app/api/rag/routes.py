"""RAG ingestion API routes with async task support."""

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse

from app.core.dependencies import AsyncSessionDep, CurrentUser
from app.models.task import Task, TaskStatus, TaskType
from app.tasks.rag_tasks import ingest_document_task

router = APIRouter()
logger = logging.getLogger(__name__)

# Directory for uploaded files (configure via settings in production)
UPLOAD_DIR = Path("/tmp/clarityql_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
        
        # ⚠️ EXCEPTIONAL CASE: Commit before queuing Celery task
        # Normally we let the session dependency handle commits, but here we MUST
        # commit before queuing because:
        # 1. The Celery worker runs in a separate process/transaction
        # 2. It needs to see the Task record immediately when it starts
        # 3. Without commit, worker's transaction won't see this uncommitted record
        # 4. This violates our usual "no manual commits" rule, but it's necessary
        #    for background task coordination
        await session.commit()

        # Queue Celery task with task.id so worker can find the record immediately
        celery_task = ingest_document_task.delay(
            task_id=str(task.id),  # Our Task model ID
            file_path=str(file_path),
            document_title=document_title,
            description=description,
            language=language,
            tenant_id=str(current_user.tenant_id),
            owner_user_id=str(current_user.id),
            max_chunk_tokens=max_chunk_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
        )

        # Update task with Celery task ID for reference
        # Re-attach to session after commit and update celery_task_id
        task.celery_task_id = celery_task.id
        session.add(task)  # Re-add to session
        await session.flush()  # Flush the update

        logger.info(
            f"Ingestion task queued: {task.id} (Celery: {celery_task.id})"
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "task_id": str(task.id),
                "celery_task_id": celery_task.id,
                "status": task.status.value,
                "message": "Document upload successful. Processing in background.",
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
                    "description": doc.description,
                    "language": doc.language,
                    "chunk_count": doc.chunk_count,
                    "source_type": doc.source_type.value,
                    "visibility": doc.visibility.value,
                    "created_at": doc.created_at.isoformat(),
                }
                for doc in documents
            ],
        }
    )
