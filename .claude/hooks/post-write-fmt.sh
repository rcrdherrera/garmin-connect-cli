#!/usr/bin/env bash
# Auto-formats newly written Python files.
# Fires via PostToolUse[Write] hook in settings.local.json.

file="${CLAUDE_TOOL_INPUT_FILE_PATH:-}"

if ! echo "$file" | grep -q '\.py$'; then
  exit 0
fi

export PATH="$HOME/.local/bin:$PATH"
cd /Users/ricardo.herrera/GitHub/garmin-connect-cli || exit 0

make fmt 2>/dev/null || true
