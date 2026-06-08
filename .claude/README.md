# Claude Code Harness — garmin-connect-cli

This directory configures Claude Code for autonomous development of this project.
It defines what Claude can do, how it responds to events, and what it knows at session start.

---

## Directory layout

```
.claude/
├── README.md               ← this file
├── settings.local.json     ← permissions + hooks (not git-tracked)
├── commands/               ← slash commands (skills)
│   ├── coach.md            ← /coach  — design + upload Garmin workouts
│   ├── deploy.md           ← /deploy — gate → push → CI → health probe
│   ├── evaluate.md         ← /evaluate — post-workout load analysis
│   ├── fix.md              ← /fix    — self-healing test/lint loop
│   └── status.md           ← /status — project health dashboard
├── hooks/                  ← shell scripts wired to hook events
│   ├── pre-commit-gate.sh  ← blocks git commit if make can-release fails
│   ├── post-write-fmt.sh   ← runs make fmt after any Python file is written/edited
│   └── post-bash-failure.sh ← logs unexpected Bash failures to memory
└── memory/                 ← persistent facts across sessions (auto-memory)
    ├── MEMORY.md           ← index of all memory files
    ├── failure_scratch.md  ← raw failure log written by post-bash-failure.sh
    └── *.md                ← typed memory files (user, project, feedback, reference)
```

> **`settings.local.json` is intentionally excluded from git.** It contains local paths and
> is machine-specific. The hooks reference absolute paths under
> `/Users/ricardo.herrera/GitHub/garmin-connect-cli/`.

---

## Slash commands

Invoke with `/command-name` in the Claude Code prompt.

### `/coach [running|strength|lower-body|upper-body|full-body|weekly]`
Science-based training coach. Reads Garmin readiness + HRV, checks the training phase,
designs appropriate workouts, uploads them to Garmin Connect, and schedules them to the
calendar. Writes the plan to `~/.config/garmin-connect-cli/training_plan.json`.

### `/evaluate`
Post-workout evaluation. Reads Garmin self-assessment, computes ACWR/CTL/ATL/TSB load
metrics, adjusts the upcoming training calendar based on how the session went.

### `/deploy`
Full deploy pipeline:
1. `make can-release` — lint + tests (gate; aborts on failure)
2. `git push origin main`
3. `gh run watch` on the **Test** workflow
4. `gh run watch` on the **Deploy Server** workflow
5. Tailscale health probe to `garmincoach-server:8765/health`

### `/fix`
Self-healing loop. Runs `make can-release`, categorizes failures (format / lint / import /
syntax / assertion / collection), applies the right fix, re-runs — up to 3 attempts.
Reports what it fixed or escalates to the user if still broken.

### `/status`
One-shot project health check (all checks run in parallel):
- Git: branch, last commit, uncommitted changes
- CI: last 5 workflow runs with status/conclusion
- Server: live `/health` probe via Tailscale
- Garmin: today's readiness snapshot
- Training plan: current phase + session completion status

---

## Hooks

Hooks fire automatically on tool events. Defined in `settings.local.json`.

### `PreToolUse[Bash]` → `pre-commit-gate.sh`
Intercepts any `git commit` command. Runs `make can-release` first.
If lint or tests fail, the commit is **blocked** and the error is surfaced.
Non-commit commands pass through immediately.

### `PostToolUse[Edit|Write]` → `post-write-fmt.sh`
After any Python file is edited or created, runs `make fmt` (ruff format + fix).
Filters on `.py` extension — no-op for markdown, JSON, shell, etc.

### `PostToolUse[Bash]` → `post-bash-failure.sh`
After Bash tool calls, checks for non-zero exit codes in unexpected commands
(skips test/lint commands where failure is normal). Appends a timestamped entry
to `memory/failure_scratch.md` for future sessions to reference.

---

## Permissions

Defined in `settings.local.json`. Broad semantic patterns — no hardcoded command strings.

| Pattern | Covers |
|---------|--------|
| `Bash(git *)` | All git operations |
| `Bash(make *)` | All Makefile targets |
| `Bash(gh *)` | GitHub CLI (CI, PRs, runs) |
| `Bash(uv run *)` | Python tooling via uv |
| `Bash(~/.local/bin/uv run *)` | uv when not on PATH |
| `Bash(obsidian *)` | Vault reads/writes |
| `Bash(curl *)` | HTTP requests (health probes, API) |
| `Bash(tailscale *)` | Network/IP resolution |
| `Bash(grep/find *)` | File search |
| `Read(//Users/ricardo.herrera/**)` | All local files |

**Additional directory:** `~/Github/Garmin-Coach` (iOS companion repo).

---

## Memory system

`memory/` stores facts that persist across sessions. Claude reads and writes these
automatically. Files follow a typed frontmatter schema (`user`, `project`, `feedback`, `reference`).

`MEMORY.md` is the index — loaded into every session context.

`failure_scratch.md` is a raw append-only log written by the failure hook. Claude
consults it at session start and promotes recurring patterns into named memory files.

**Do not** store code patterns, git history, or ephemeral task state in memory.
These are better derived from the live codebase.

---

## Autonomy contract

See the full table in `AGENTS.md` → **Autonomy Boundaries**.

Summary:
- **Green (act freely):** read, edit, test, format, lint, git status/diff/log
- **Yellow (act and announce):** commit, push, install deps, watch CI
- **Red (always confirm):** force push, DB schema changes, production env edits, deleting files not created this session

When in doubt: announce and confirm rather than act silently.

---

## Scheduled agents

### Server health check (active)

An hourly systemd timer runs **on the server itself** (not a remote cloud agent — Tailscale
isn't available in cloud sandboxes).

| File | Purpose |
|------|---------|
| `healthcheck.sh` | Curls `localhost:8765/health`; sends Telegram message if down |
| `garmincoach-healthcheck.service` | Oneshot systemd unit that runs the script |
| `garmincoach-healthcheck.timer` | Fires 2min after boot, then every hour |
| `setup_healthcheck.sh` | One-time installer — run once on server via SSH |

**Setup**: `sudo bash /opt/garmin-connect-cli/setup_healthcheck.sh <telegram-token> <chat-id>`
**Credentials**: `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` stored in `/etc/garmincoach.env`

### Planned
- Weekly context refresh — sync latest training facts from DB into vault wiki

---

## Adding a new skill

1. Create `.claude/commands/<name>.md` with frontmatter:
   ```markdown
   ---
   description: One-line description shown in skill list
   argument-hint: [optional|args]
   allowed-tools: [Bash, Read, Edit, Write]
   ---
   ```
2. Write the prompt body — step-by-step instructions Claude follows when invoked.
3. The skill appears immediately as `/<name>` in the Claude Code prompt.

## Adding a new hook

1. Create `.claude/hooks/<name>.sh`, make it executable (`chmod +x`).
2. Read `CLAUDE_TOOL_INPUT_*` env vars for tool input.
3. For `PostToolUse`, the tool result JSON is passed on stdin — use `cat` + `jq` to parse.
4. Exit non-zero in a `PreToolUse` hook to **block** the tool call.
5. Wire it in `settings.local.json` under the appropriate `PreToolUse`/`PostToolUse` event.
