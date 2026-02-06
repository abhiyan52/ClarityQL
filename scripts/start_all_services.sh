#!/usr/bin/env bash
#
# Complete startup script for ClarityQL RAG system
# Starts all required services in the correct order
#

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🚀 Starting ClarityQL RAG System..."
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "✓ .env created. Please fill in your API keys."
    echo ""
fi

# Function to check if a service is running
check_service() {
    local service=$1
    local check_cmd=$2
    
    if eval "$check_cmd" > /dev/null 2>&1; then
        echo "✓ $service is running"
        return 0
    else
        echo "❌ $service is not running"
        return 1
    fi
}

# ──────────────────────────────────────────────────────────────────────
# 1. Check PostgreSQL
# ──────────────────────────────────────────────────────────────────────
echo "1️⃣  Checking PostgreSQL..."
if check_service "PostgreSQL" "psql -h 127.0.0.1 -U postgres -d clarityql -c 'SELECT 1' 2>/dev/null"; then
    echo ""
else
    echo "   Start with: brew services start postgresql@14"
    echo "   Or use Docker: cd infra && docker-compose up -d postgres"
    echo ""
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# 2. Check Redis
# ──────────────────────────────────────────────────────────────────────
echo "2️⃣  Checking Redis..."
if check_service "Redis" "redis-cli ping"; then
    echo ""
else
    echo "   Start with: brew services start redis"
    echo "   Or use Docker: cd infra && docker-compose up -d redis"
    echo ""
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# 3. Run Database Migrations
# ──────────────────────────────────────────────────────────────────────
echo "3️⃣  Running database migrations..."
cd apps/backend
uv run alembic upgrade head
echo "✓ Migrations complete"
echo ""
cd "$PROJECT_ROOT"

# ──────────────────────────────────────────────────────────────────────
# 4. Start Services
# ──────────────────────────────────────────────────────────────────────
echo "4️⃣  Starting services..."
echo ""
echo "Starting in separate terminal windows:"
echo ""
echo "   Terminal 1: FastAPI Server"
echo "   Terminal 2: Celery Worker"
echo ""
echo "Run these commands:"
echo ""
echo "   # Terminal 1 - API Server"
echo "   cd $PROJECT_ROOT"
echo "   ./scripts/start_api_server.sh"
echo ""
echo "   # Terminal 2 - Celery Worker"
echo "   cd $PROJECT_ROOT"
echo "   ./scripts/start_celery_worker.sh"
echo ""
echo "──────────────────────────────────────────────────────────────"
echo ""
echo "Once both are running, access:"
echo "   • API:  http://localhost:8000"
echo "   • Docs: http://localhost:8000/docs"
echo ""
echo "Test the system:"
echo "   cd $PROJECT_ROOT/scripts"
echo "   ./test_rag_flow.sh"
echo ""
