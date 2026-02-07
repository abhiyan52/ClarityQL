#!/usr/bin/env bash
#
# Start FastAPI server for ClarityQL
#

set -e

echo "Starting ClarityQL API Server..."

# Navigate to backend directory
cd "$(dirname "$0")/../apps/backend"

# Set Python path to include project root (so packages/ can be imported)
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../.."

# Load environment variables
if [ -f "../../.env" ]; then
    echo "Loading environment variables from .env"
    # Use set -a to export all variables from .env
    set -a
    source ../../.env
    set +a
fi

echo ""
echo "Starting server on http://localhost:8000"
echo "Docs available at http://localhost:8000/docs"
echo ""

# Start uvicorn with auto-reload
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
