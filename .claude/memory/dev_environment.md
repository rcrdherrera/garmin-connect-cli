---
name: dev-environment
description: Windows dev setup with Warp terminal; jq required for Warp Claude Code plugin; two-repo workflow friction; Mac migration under consideration
metadata: 
  node_type: memory
  type: project
  originSessionId: 9ddafaf0-4c84-4a1f-84c8-f4a11e1e496c
---

**Terminal:** Warp on Windows (Git Bash shell inside Warp)

**Warp + Claude Code plugin requires `jq`**
- Stop hook error: `jq: command not found` + `/dev/tty: No such device or address`
- Fix: `winget install jqlang.jq`, then restart Warp
- If Git Bash doesn't pick up winget's jq: copy `jq.exe` to `C:\Program Files\Git\usr\bin\`

**Two-repo workflow (current friction point)**
- `C:\garmin-connect-cli` — Python backend (Garmin API, FastAPI server, coaching logic); primary Claude Code session lives here; all memory anchored here
- `C:\Users\ricar\Github\Garmin-Coach` — Swift/HealthKit iOS app; changes triggered from garmin-connect-cli session; must push → pull on Mac for Xcode to build

**Why:** iOS changes can only be compiled on Mac with Xcode, but development happens on Windows — requires a git sync step every time.

**Mac migration under consideration** — would eliminate the sync problem entirely; Xcode and Claude Code on same machine. Would require re-establishing Python env + Garmin auth on Mac and migrating memory files from `~/.claude/projects/C--garmin-connect-cli/memory/` to the Mac equivalent path.

**How to apply:** If suggesting workflow changes or new features that affect both repos, flag the sync overhead. If user has moved to Mac, remind them to migrate memory files.
