# ClarityQL

ClarityQL is a Natural Language Query (NLQ) analytics platform designed to translate user intent into safe, explainable data queries and visual insights. This repository is a production-grade monorepo that supports multiple NLQ use cases while sharing common infrastructure and domain logic.

**Status:** Bootstrap scaffold (no business logic implemented yet).

## Architecture Summary

- **apps/backend**: FastAPI service exposing NLQ APIs, auth stubs, and schema endpoints.
- **apps/frontend**: Vite + React + TypeScript client with placeholder pages.
- **packages/core**: Framework-agnostic domain modules (schema registry, SQL AST, safety checks, visualization inference, explainability).
- **packages/auth**: JWT helper stubs for shared auth utilities.
- **packages/db**: Database base + migration scaffolding.
- **infra**: Local development infrastructure via Docker Compose.
- **scripts**: Seed utilities for initial data.

## Run Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (optional, for local Postgres/Redis)
- uv (for Python dependency management)

### Backend

```bash
uv venv
uv sync
cp .env.example .env
uv run --directory apps/backend -- python -m uvicorn app.main:app --reload
```

### Frontend

```bash
cd apps/frontend
npm install
npm run dev
```

### Infrastructure

```bash
docker compose -f infra/docker-compose.yml up
```

### UV Scripts

```bash
./scripts/run_backend.sh
./scripts/lint.sh
./scripts/format.sh
```

## Folder Structure

```
apps/
  backend/      # FastAPI application
  frontend/     # React (Vite + TypeScript)
packages/
  core/         # Domain logic (framework-agnostic)
  auth/         # JWT helpers
  db/           # DB base + migrations
infra/          # Docker Compose
scripts/        # Utility scripts
```
