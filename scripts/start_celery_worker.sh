#!/usr/bin/env bash
#
# Start Celery worker for ClarityQL RAG processing
#

set -e

echo "Starting Celery worker for ClarityQL..."

# Navigate to backend directory
cd "$(dirname "$0")/../apps/backend"

# Set Python path to include project root (so packages/ can be imported)
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../.."

# Load environment variables
if [ -f "../../.env" ]; then
    echo "Loading environment variables from .env"
    set -a
    source ../../.env
    set +a
fi

# macOS-specific: Set environment variable to avoid fork issues
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Start Celery worker
echo "Starting Celery worker with:"
echo "  - Broker: ${CELERY_BROKER_URL:-redis://127.0.0.1:6379/0}"
echo "  - Backend: Database"
echo "  - Queues: rag_ingestion, rag_embeddings, rag_query, nlq, celery"
echo "  - Pool: solo (to avoid macOS fork issues)"

uv run celery -A app.core.celery_app:celery_app worker \
    --loglevel=info \
    --pool=solo \
    --queues=rag_ingestion,rag_embeddings,rag_query,nlq,celery \
    --max-tasks-per-child=50 \
    --task-events \
    --without-gossip \
    --without-mingle \
    --without-heartbeat

# Alternative with autoreload for development:
# uv run watchfiles --filter python 'celery -A app.core.celery_app:celery_app worker --loglevel=info --pool=solo --queues=rag_ingestion,rag_embeddings,rag_query,nlq,celery'
