#!/usr/bin/env bash
set -euo pipefail

uv run --directory apps/backend -- python -m uvicorn app.main:app --reload
