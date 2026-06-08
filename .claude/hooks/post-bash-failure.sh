#!/usr/bin/env bash
# Logs unexpected Bash failures to failure_scratch.md for future sessions.
# Fires via PostToolUse[Bash] hook in settings.local.json.
# "Unexpected" = non-zero exit on commands that aren't tests/lint (those failing is normal).

cmd="${CLAUDE_TOOL_INPUT_COMMAND:-}"

# Skip expected-to-fail commands
if echo "$cmd" | grep -qE 'make (test|lint|can-release)|pytest|ruff|grep|find'; then
  exit 0
fi

# Read the tool output from stdin (Claude Code passes PostToolUse result as JSON)
raw=$(cat 2>/dev/null)

# Check for non-zero exit in output
if ! echo "$raw" | grep -qE '"exit_code":\s*[1-9]|Exit code [1-9]|error:.*exit [1-9]'; then
  exit 0
fi

# Log the failure
log=/Users/ricardo.herrera/.claude/projects/-Users-ricardo-herrera-GitHub-garmin-connect-cli/memory/failure_scratch.md
timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

{
  echo ""
  echo "## $timestamp"
  echo "**Command:** \`$cmd\`"
  echo ""
} >> "$log" 2>/dev/null || true
