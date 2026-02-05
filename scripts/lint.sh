#!/usr/bin/env bash
set -euo pipefail

uv run -- ruff check apps/backend packages scripts
