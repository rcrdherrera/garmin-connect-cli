---
name: dev-environment
description: Mac dev environment confirmed as of 2026-06-02; both repos on Mac at /Users/ricardo.herrera/GitHub/
metadata:
  type: project
---

**Machine:** Mac (Darwin 25.5.0), shell zsh. Migration from Windows is complete.

**Both repos on Mac:**
- `/Users/ricardo.herrera/GitHub/garmin-connect-cli` — Python backend + FastAPI server; all Claude Code memory anchored here
- `/Users/ricardo.herrera/GitHub/Garmin-Coach` — Swift/SwiftUI iOS app; Xcode available on same machine, no sync step needed

**Runtime:** `uv` manages Python 3.13 for the CLI project. Xcode available locally for iOS builds.

**Previous Windows friction is gone** — the old workflow required pushing from Windows and pulling on Mac to compile. That no longer applies.

**How to apply:** No need to flag sync overhead when suggesting changes that touch both repos. Xcode builds can be suggested directly.
