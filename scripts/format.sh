#!/usr/bin/env bash
set -euo pipefail

uv run -- ruff format apps/backend packages scripts
uv run -- black apps/backend packages scripts
