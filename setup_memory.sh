#!/usr/bin/env bash
# Link Claude Code's project memory to the in-repo .claude/memory/ directory.
# Run once after cloning on a new machine:
#   bash setup_memory.sh
#
# This makes Claude Code read/write memory from the repo so it travels with git.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_SRC="${REPO_DIR}/.claude/memory"

if [[ ! -d "$MEMORY_SRC" ]]; then
    echo "Error: .claude/memory not found in repo at $REPO_DIR"
    exit 1
fi

# Claude Code encodes the project path by replacing / with - (dropping leading /)
ENCODED="$(echo "$REPO_DIR" | sed 's|^/|-|; s|/|-|g')"
CLAUDE_MEMORY_DIR="${HOME}/.claude/projects/${ENCODED}/memory"

echo "Repo:          $REPO_DIR"
echo "Encoded path:  $ENCODED"
echo "Target:        $CLAUDE_MEMORY_DIR"
echo ""

# Create parent dir if needed
mkdir -p "$(dirname "$CLAUDE_MEMORY_DIR")"

# Replace or create the memory dir as a symlink
if [[ -L "$CLAUDE_MEMORY_DIR" ]]; then
    echo "Symlink already exists — updating..."
    rm "$CLAUDE_MEMORY_DIR"
elif [[ -d "$CLAUDE_MEMORY_DIR" ]]; then
    echo "Existing memory dir found — backing up to ${CLAUDE_MEMORY_DIR}.bak"
    mv "$CLAUDE_MEMORY_DIR" "${CLAUDE_MEMORY_DIR}.bak"
fi

ln -s "$MEMORY_SRC" "$CLAUDE_MEMORY_DIR"
echo "Symlink created: $CLAUDE_MEMORY_DIR -> $MEMORY_SRC"
echo ""
echo "Done. Claude Code will now read/write memory from the repo."
