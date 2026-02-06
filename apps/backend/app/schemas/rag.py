"""Pydantic schemas for RAG ingestion pipeline."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Source Document Metadata
# ──────────────────────────────────────────────────────────────────────


class DocumentSourceType(str, Enum):
    """How the document was ingested."""

    UPLOADED = "uploaded"
    SYSTEM = "system"
    WEB = "web"


class SupportedFileType(str, Enum):
    """Supported document types for ingestion."""

    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    HTML = "html"
    TXT = "txt"
    MD = "md"
    IMAGE = "image"  # Scanned images with OCR


class DocumentProcessingStatus(str, Enum):
    """Processing status for document ingestion pipeline."""

    UPLOADED = "uploaded"  # File uploaded, not yet processed
    PARSING = "parsing"  # Document is being parsed (Docling)
    PARSED = "parsed"  # Document parsed successfully
    CHUNKING = "chunking"  # Document is being chunked
    CHUNKED = "chunked"  # Document chunked successfully
    EMBEDDING = "embedding"  # Embeddings are being generated
    READY = "ready"  # Document is fully processed and ready for search
    FAILED = "failed"  # Processing failed at any stage


# ──────────────────────────────────────────────────────────────────────
# Chunk Metadata
# ──────────────────────────────────────────────────────────────────────


class ChunkMetadata(BaseModel):
    """
    Rich metadata for a single chunk.

    Provides full traceability back to the source document and location.
    """

    # Source document
    document_id: Optional[UUID] = Field(
        None,
        description="ID of the parent document (set after DB insertion)",
    )
    document_title: str = Field(..., description="Title of the source document")
    file_name: str = Field(..., description="Original file name")

    # Location within document
    page_number: Optional[int] = Field(
        None,
        description="Page number where this chunk originates (1-indexed)",
    )
    section_title: Optional[str] = Field(
        None,
        description="Section heading this chunk belongs to",
    )
    heading_level: Optional[int] = Field(
        None,
        description="Heading hierarchy level (H1=1, H2=2, etc.)",
    )

    # Chunk properties
    chunk_index: int = Field(
        ...,
        description="0-based position of this chunk within the document",
    )
    token_count: int = Field(..., description="Number of tokens in the chunk")

    # Language and processing
    language: str = Field(default="en", description="Detected language (ISO 639-1)")
    element_type: Optional[str] = Field(
        None,
        description="Semantic element type from Docling (e.g., 'paragraph', 'list_item')",
    )

    # Extensible metadata
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom metadata",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_title": "Q4 Financial Report",
                "file_name": "Q4_2024_Report.pdf",
                "page_number": 12,
                "section_title": "Revenue Analysis",
                "heading_level": 2,
                "chunk_index": 45,
                "token_count": 387,
                "language": "en",
                "element_type": "paragraph",
            }
        }


# ──────────────────────────────────────────────────────────────────────
# Processed Chunk (Embedding-Ready)
# ──────────────────────────────────────────────────────────────────────


class ProcessedChunk(BaseModel):
    """
    A single chunk ready for embedding.

    Self-contained unit with text content and full metadata for traceability.
    """

    content: str = Field(
        ...,
        description="Clean text content of the chunk",
        min_length=1,
    )
    metadata: ChunkMetadata = Field(..., description="Rich metadata for this chunk")

    @property
    def context_string(self) -> str:
        """
        Generate a context-enriched string for embedding.

        Prepends section context to help with retrieval relevance.
        """
        parts = []

        if self.metadata.section_title:
            parts.append(f"Section: {self.metadata.section_title}")

        if self.metadata.page_number:
            parts.append(f"Page {self.metadata.page_number}")

        if parts:
            context = " | ".join(parts)
            return f"[{context}]\n\n{self.content}"

        return self.content

    class Config:
        json_schema_extra = {
            "example": {
                "content": "Revenue increased by 23% YoY driven by strong performance in the enterprise segment...",
                "metadata": {
                    "document_title": "Q4 Financial Report",
                    "file_name": "Q4_2024_Report.pdf",
                    "page_number": 12,
                    "section_title": "Revenue Analysis",
                    "chunk_index": 45,
                    "token_count": 387,
                    "language": "en",
                },
            }
        }


# ──────────────────────────────────────────────────────────────────────
# Ingestion Request & Response
# ──────────────────────────────────────────────────────────────────────


class IngestionRequest(BaseModel):
    """Request to ingest a document into the RAG system."""

    file_path: str = Field(
        ...,
        description="Path to the document file (local or object storage)",
    )
    document_title: Optional[str] = Field(
        None,
        description="Override document title (defaults to filename)",
    )
    description: Optional[str] = Field(
        None,
        description="Optional document description",
    )
    source_type: DocumentSourceType = Field(
        default=DocumentSourceType.UPLOADED,
        description="How the document was sourced",
    )
    language: Optional[str] = Field(
        None,
        description="Override language (auto-detected if not provided)",
    )
    tenant_id: Optional[UUID] = Field(
        None,
        description="Tenant ID (defaults to user's tenant)",
    )
    owner_user_id: Optional[UUID] = Field(
        None,
        description="Owner user ID (defaults to requesting user)",
    )

    # Chunking parameters
    max_chunk_tokens: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Maximum tokens per chunk",
    )
    chunk_overlap_tokens: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Overlap tokens between adjacent chunks",
    )


class IngestionStats(BaseModel):
    """Statistics about the ingestion process."""

    total_chunks: int = Field(..., description="Number of chunks created")
    total_tokens: int = Field(..., description="Total tokens across all chunks")
    avg_tokens_per_chunk: float = Field(
        ...,
        description="Average tokens per chunk",
    )
    pages_processed: Optional[int] = Field(
        None,
        description="Number of pages in the document",
    )
    language_detected: str = Field(..., description="Detected document language")


class IngestionResponse(BaseModel):
    """Response after successful document ingestion."""

    document_id: UUID = Field(..., description="ID of the created document")
    chunks_created: int = Field(..., description="Number of chunks created")
    processing_status: DocumentProcessingStatus = Field(
        ...,
        description="Current processing status of the document"
    )
    stats: IngestionStats = Field(..., description="Ingestion statistics")
    processing_time_ms: float = Field(
        ...,
        description="Total processing time in milliseconds",
    )
    created_at: datetime = Field(..., description="Timestamp of ingestion")

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "chunks_created": 127,
                "processing_status": "chunked",
                "stats": {
                    "total_chunks": 127,
                    "total_tokens": 45890,
                    "avg_tokens_per_chunk": 361.3,
                    "pages_processed": 42,
                    "language_detected": "en",
                },
                "processing_time_ms": 2847.5,
                "created_at": "2024-02-06T14:30:00Z",
            }
        }
