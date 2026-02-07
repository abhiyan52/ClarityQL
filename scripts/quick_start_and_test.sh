#!/usr/bin/env bash
#
# Quick start script - starts all services and runs RAG test
#

set -e

PROJECT_ROOT="/Users/abhiyantimilsina/Desktop/ClarityQL"
cd "$PROJECT_ROOT"

echo "════════════════════════════════════════════════════════════════"
echo "ClarityQL RAG Pipeline - Quick Start"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Function to check if process is running
check_process() {
  local name=$1
  local pattern=$2
  if pgrep -f "$pattern" > /dev/null; then
    echo "✅ $name is running"
    return 0
  else
    echo "⚠️  $name is not running"
    return 1
  fi
}

# Function to wait for service
wait_for_service() {
  local name=$1
  local url=$2
  local max_attempts=30
  
  echo "Waiting for $name..."
  for i in $(seq 1 $max_attempts); do
    if curl -s "$url" > /dev/null 2>&1; then
      echo "✅ $name is ready"
      return 0
    fi
    sleep 1
  done
  echo "❌ $name did not start within 30 seconds"
  return 1
}

echo "Checking services..."
echo ""

# Check PostgreSQL
if ! docker ps | grep -q postgres; then
  echo "Starting PostgreSQL..."
  docker compose -f infra/docker-compose.yml up -d postgres
  sleep 5
fi

# Check Redis
if ! docker ps | grep -q redis; then
  echo "Starting Redis..."
  docker compose -f infra/docker-compose.yml up -d redis
  sleep 2
fi

# Check backend
if ! check_process "Backend API" "uvicorn.*app.main:app"; then
  echo "Starting backend API..."
  ./scripts/start_api_server.sh > /dev/null 2>&1 &
  wait_for_service "Backend API" "http://localhost:8000/health"
fi

# Check Celery
if ! check_process "Celery worker" "celery.*worker"; then
  echo "Starting Celery worker..."
  ./scripts/start_celery_worker.sh > /dev/null 2>&1 &
  sleep 5
  echo "✅ Celery worker started"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "All services are running!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Backend API: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""

# Run test
echo "Running RAG pipeline test..."
echo ""
./scripts/test_rag_pipeline.sh

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ Quick start complete!"
echo "════════════════════════════════════════════════════════════════"
