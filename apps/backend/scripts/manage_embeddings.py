#!/usr/bin/env python3
"""
Command-line utility to manage RAG document embeddings.

This script provides convenient commands to:
- Generate embeddings for specific documents
- Process pending documents
- Check document status
- Batch process multiple documents
"""

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
sys.path.insert(0, "/Users/abhiyantimilsina/Desktop/ClarityQL/apps/backend")

from app.core.config import get_settings
from app.models.document import Document, DocumentProcessingStatus
from app.tasks.rag_tasks import (
    generate_embeddings_task,
    generate_embeddings_batch_task,
    generate_embeddings_for_pending_documents_task,
)

settings = get_settings()


async def get_document_status(document_id: str):
    """Get status of a specific document."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            doc_uuid = UUID(document_id)
            result = await session.execute(
                select(Document).where(Document.id == doc_uuid)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                print(f"❌ Document {document_id} not found")
                return

            print(f"\n📄 Document: {doc.title}")
            print(f"   ID: {doc.id}")
            print(f"   Status: {doc.processing_status.value}")
            print(f"   Chunks: {doc.chunk_count}")
            print(f"   Language: {doc.language}")
            print(f"   Created: {doc.created_at}")

            if doc.processing_error:
                print(f"   ⚠️  Error: {doc.processing_error}")

        except ValueError:
            print(f"❌ Invalid document ID format: {document_id}")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await engine.dispose()


async def list_pending_documents():
    """List all documents waiting for embeddings."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            result = await session.execute(
                select(Document)
                .where(
                    Document.processing_status == DocumentProcessingStatus.CHUNKED,
                    Document.is_active == True,
                )
                .order_by(Document.created_at.desc())
            )
            documents = result.scalars().all()

            if not documents:
                print("✅ No pending documents found")
                return

            print(f"\n📋 Found {len(documents)} documents pending embeddings:\n")
            for doc in documents:
                print(f"  • {doc.title}")
                print(f"    ID: {doc.id}")
                print(f"    Chunks: {doc.chunk_count}")
                print(f"    Created: {doc.created_at}")
                print()

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await engine.dispose()


def generate_embeddings(document_id: str, force: bool = False):
    """Queue embedding generation for a specific document."""
    try:
        doc_uuid = UUID(document_id)
        print(f"\n🚀 Queueing embedding generation for document {document_id}")

        if force:
            print("   ⚠️  Force mode: will clear existing embeddings")

        result = generate_embeddings_task.delay(document_id=str(doc_uuid))
        print(f"✅ Task queued successfully!")
        print(f"   Celery Task ID: {result.id}")
        print(f"\n   Track progress with: celery -A app.core.celery_app result {result.id}")

    except ValueError:
        print(f"❌ Invalid document ID format: {document_id}")
    except Exception as e:
        print(f"❌ Error: {e}")


def generate_batch(document_ids: list[str]):
    """Queue batch embedding generation for multiple documents."""
    print(f"\n🚀 Queueing batch embedding generation for {len(document_ids)} documents")

    try:
        result = generate_embeddings_batch_task.delay(
            document_ids=document_ids, batch_size=32
        )
        print(f"✅ Batch task queued successfully!")
        print(f"   Celery Task ID: {result.id}")
        print(f"\n   Track progress with: celery -A app.core.celery_app result {result.id}")

    except Exception as e:
        print(f"❌ Error: {e}")


def process_pending():
    """Queue processing for all pending documents."""
    print("\n🚀 Queueing processing for all pending documents")

    try:
        result = generate_embeddings_for_pending_documents_task.delay()
        print(f"✅ Task queued successfully!")
        print(f"   Celery Task ID: {result.id}")
        print(
            f"\n   Track progress with: celery -A app.core.celery_app result {result.id}"
        )

    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage RAG document embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check document status
  %(prog)s status 550e8400-e29b-41d4-a716-446655440000

  # List pending documents
  %(prog)s list-pending

  # Generate embeddings for a document
  %(prog)s generate 550e8400-e29b-41d4-a716-446655440000

  # Force regenerate embeddings
  %(prog)s generate 550e8400-e29b-41d4-a716-446655440000 --force

  # Batch generate for multiple documents
  %(prog)s batch 550e8400-... 660e8400-... 770e8400-...

  # Process all pending documents
  %(prog)s process-pending
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check document status")
    status_parser.add_argument("document_id", help="Document UUID")

    # List pending command
    subparsers.add_parser("list-pending", help="List documents pending embeddings")

    # Generate command
    generate_parser = subparsers.add_parser(
        "generate", help="Generate embeddings for a document"
    )
    generate_parser.add_argument("document_id", help="Document UUID")
    generate_parser.add_argument(
        "--force", action="store_true", help="Force regeneration of existing embeddings"
    )

    # Batch command
    batch_parser = subparsers.add_parser(
        "batch", help="Generate embeddings for multiple documents"
    )
    batch_parser.add_argument(
        "document_ids", nargs="+", help="List of document UUIDs"
    )

    # Process pending command
    subparsers.add_parser(
        "process-pending", help="Process all documents pending embeddings"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Execute command
    if args.command == "status":
        asyncio.run(get_document_status(args.document_id))
    elif args.command == "list-pending":
        asyncio.run(list_pending_documents())
    elif args.command == "generate":
        generate_embeddings(args.document_id, args.force)
    elif args.command == "batch":
        generate_batch(args.document_ids)
    elif args.command == "process-pending":
        process_pending()


if __name__ == "__main__":
    main()
