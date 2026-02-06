"""RAG query service for semantic search and retrieval."""

import logging
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.conversation import Conversation
from app.models.conversation_state import ConversationState
from app.models.document import Document
from app.services.rag.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class RAGQueryService:
    """
    Service for RAG (Retrieval-Augmented Generation) queries.
    
    Handles:
    - Query embedding generation
    - Semantic search via vector similarity
    - Context retrieval from documents
    - Conversation state management
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = get_embedding_service()

    async def query(
        self,
        query: str,
        tenant_id: UUID,
        user_id: UUID,
        document_ids: List[UUID] | None = None,
        conversation_id: UUID | None = None,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> dict:
        """
        Execute a RAG query: embed query, find similar chunks, return results.

        Args:
            query: User's natural language query
            tenant_id: Tenant ID for multi-tenancy filtering
            user_id: User ID for conversation ownership
            document_ids: Optional list of document IDs to search within (None = all)
            conversation_id: Optional conversation ID for context continuity
            top_k: Number of top results to return (default: 5)
            min_similarity: Minimum similarity threshold 0-1 (default: 0.0)

        Returns:
            dict with:
                - conversation_id: UUID of conversation
                - query: Original query text
                - chunks: List of matching chunks with scores
                - documents: Document metadata for matched chunks
        """
        logger.info(
            f"RAG query: '{query[:50]}...' for tenant {tenant_id}, "
            f"docs={document_ids}, top_k={top_k}"
        )

        # 1. Get or create conversation
        conversation = await self._get_or_create_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # 2. Generate query embedding
        query_embedding = self.embedding_service.encode(query)
        embedding_list = query_embedding.tolist()

        # 3. Build similarity search query
        query_obj = self._build_similarity_query(
            embedding=embedding_list,
            tenant_id=tenant_id,
            document_ids=document_ids,
            top_k=top_k,
        )

        # 4. Execute search
        result = await self.session.execute(query_obj)
        chunks_with_scores = result.all()

        # 5. Filter by minimum similarity if specified
        if min_similarity > 0.0:
            chunks_with_scores = [
                (chunk, score)
                for chunk, score in chunks_with_scores
                if (1 - score) >= min_similarity  # cosine distance to similarity
            ]

        # 6. Get document metadata for matched chunks
        document_map = await self._get_documents_for_chunks(
            [chunk.document_id for chunk, _ in chunks_with_scores]
        )

        # 7. Format response
        formatted_chunks = [
            {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "document_title": document_map.get(chunk.document_id, {}).get(
                    "title", "Unknown"
                ),
                "content": chunk.content,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "chunk_index": chunk.chunk_index,
                "similarity_score": 1 - score,  # Convert distance to similarity
                "token_count": chunk.token_count,
            }
            for chunk, score in chunks_with_scores
        ]

        return {
            "conversation_id": str(conversation.id),
            "query": query,
            "chunks": formatted_chunks,
            "documents": list(document_map.values()),
            "total_chunks_found": len(formatted_chunks),
        }

    def _build_similarity_query(
        self,
        embedding: List[float],
        tenant_id: UUID,
        document_ids: List[UUID] | None,
        top_k: int,
    ):
        """
        Build a pgvector similarity search query.

        Uses cosine distance operator <=> for similarity ranking.
        """
        # Start with base query
        query = (
            select(
                Chunk,
                Chunk.embedding.cosine_distance(embedding).label("distance"),
            )
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.embedding.isnot(None),  # Only chunks with embeddings
            )
        )

        # Filter by document IDs if provided
        if document_ids:
            query = query.where(Chunk.document_id.in_(document_ids))

        # Order by similarity (lower distance = higher similarity)
        query = query.order_by("distance").limit(top_k)

        return query

    async def _get_documents_for_chunks(
        self, document_ids: List[UUID]
    ) -> dict[UUID, dict]:
        """Get document metadata for a list of document IDs."""
        if not document_ids:
            return {}

        result = await self.session.execute(
            select(Document).where(Document.id.in_(document_ids))
        )
        documents = result.scalars().all()

        return {
            doc.id: {
                "document_id": str(doc.id),
                "title": doc.title,
                "description": doc.description,
                "language": doc.language,
                "chunk_count": doc.chunk_count,
            }
            for doc in documents
        }

    async def _get_or_create_conversation(
        self,
        conversation_id: UUID | None,
        user_id: UUID,
    ) -> Conversation:
        """
        Get existing conversation or create a new one.

        Args:
            conversation_id: Optional existing conversation ID
            user_id: User ID for ownership

        Returns:
            Conversation object

        Raises:
            PermissionError: If conversation exists but user is not owner
        """
        if conversation_id:
            # Fetch existing conversation
            result = await self.session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Verify ownership
            if conversation.user_id != user_id:
                raise PermissionError(
                    f"User {user_id} does not own conversation {conversation_id}"
                )

            return conversation
        else:
            # Create new conversation
            conversation = Conversation(user_id=user_id)
            self.session.add(conversation)
            await self.session.flush()  # Get ID
            await self.session.refresh(conversation)
            return conversation

    async def save_conversation_context(
        self,
        conversation_id: UUID,
        context: dict,
    ):
        """
        Save conversation context (for future use with LLM integration).

        Args:
            conversation_id: Conversation ID
            context: Context data to save (e.g., retrieved chunks, generated answer)
        """
        # Check if state exists
        result = await self.session.execute(
            select(ConversationState).where(
                ConversationState.conversation_id == conversation_id
            )
        )
        state = result.scalar_one_or_none()

        if state:
            # Update existing
            state.ast_json = context
        else:
            # Create new
            state = ConversationState(
                conversation_id=conversation_id,
                ast_json=context,
            )
            self.session.add(state)

        await self.session.flush()
