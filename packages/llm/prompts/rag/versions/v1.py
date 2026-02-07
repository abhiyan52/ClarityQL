"""Version 1 of the RAG answer generation prompt."""

from langchain_core.prompts import ChatPromptTemplate

from packages.llm.prompts.rag.base import BaseRAGAnswerPrompt
from packages.llm.prompts.rag.registry import RAGAnswerPromptRegistry


@RAGAnswerPromptRegistry.register
class RAGAnswerPromptV1(BaseRAGAnswerPrompt):
    """
    Initial version of the RAG answer generation prompt.

    This prompt instructs the LLM to generate natural language answers
    based on retrieved document chunks.
    """

    version = "v1"
    description = "Initial RAG answer generation prompt"

    def build(
        self,
        query: str,
        chunks_context: str,
        conversation_history: str | None = None,
    ) -> ChatPromptTemplate:
        """Build the v1 prompt template."""
        system_message = """You are a helpful assistant that answers questions based on provided document excerpts.

Your task is to generate a clear, concise, and informative answer based solely on the provided document chunks.

IMPORTANT RULES:
1. Answer ONLY based on the provided document chunks. Do not use external knowledge.
2. If the chunks don't contain enough information to answer the query, say so clearly.
3. Cite sources when relevant by mentioning document titles or page numbers.
4. Be conversational and natural, but accurate.
5. If multiple chunks contain relevant information, synthesize them into a coherent answer.
6. Keep your answer concise but complete - typically 2-4 sentences unless more detail is needed.
7. If the query asks about something not covered in the chunks, politely indicate that the information isn't available in the provided documents.

Answer format:
- Start with a direct answer to the question
- Provide relevant details from the chunks
- Mention source documents if helpful
- Be clear if information is missing"""

        user_message_parts = [
            "USER QUERY:",
            "{query}",
            "",
            "DOCUMENT EXCERPTS:",
            "{chunks_context}",
        ]

        if conversation_history:
            user_message_parts.extend([
                "",
                "CONVERSATION HISTORY:",
                "{conversation_history}",
            ])

        user_message = "\n".join(user_message_parts)

        return ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", user_message),
        ]).partial(
            query=query,
            chunks_context=chunks_context,
            conversation_history=conversation_history or "",
        )
