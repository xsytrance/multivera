#!/usr/bin/env bash
set -euo pipefail

# MultiVera FastAPI backend startup script
# Usage: ./run_backend.sh

cd "$(dirname "$0")"

# Ensure parent dir is on PYTHONPATH so engine.py / hackermouth_rag.py are importable
export PYTHONPATH="${PYTHONPATH:-$(pwd)}"

# Optional: migrate JSON data before starting
# Uncomment to auto-run migration on every start:
# python3 backend/migrate_json_to_db.py

echo "Starting MultiVera FastAPI backend..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
