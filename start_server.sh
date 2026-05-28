#!/usr/bin/env bash
# GarminCoach home server — Ubuntu startup script
# First run: uv sync --extra server
# Then: bash start_server.sh
#
# Secrets are loaded from .env in this directory (never committed).
# Copy .env.example to .env and fill in the values.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/.env"
    set +a
fi

: "${COACH_SERVER_TOKEN:?COACH_SERVER_TOKEN must be set in .env or environment}"
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set in .env or environment}"

export COACH_PORT="${COACH_PORT:-8765}"
export COACH_HOST="${COACH_HOST:-0.0.0.0}"

echo "Starting GarminCoach server on ${COACH_HOST}:${COACH_PORT}..."
exec uv run python "$SCRIPT_DIR/server.py"
