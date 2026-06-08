#!/usr/bin/env bash
# Blocks git commit if make can-release fails.
# Fires via PreToolUse[Bash] hook in settings.local.json.

cmd="${CLAUDE_TOOL_INPUT_COMMAND:-}"

# Only gate on git commit commands
if ! echo "$cmd" | grep -qE '(^|[;&|]\s*)git(\s+-C\s+\S+)?\s+commit'; then
  exit 0
fi

export PATH="$HOME/.local/bin:$PATH"
cd /Users/ricardo.herrera/GitHub/garmin-connect-cli || exit 0

echo "⏳ Pre-commit gate: running make can-release..."
if make can-release; then
  echo "✅ Gate passed — proceeding with commit."
  exit 0
else
  echo "❌ Gate failed — fix lint/test errors before committing."
  exit 1
fi
