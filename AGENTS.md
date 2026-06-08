# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project Overview

garmin-connect-cli lets you access Garmin Connect from your terminal. Pipe it, script it, automate it. Supports multiple output formats (JSON, JSONL, CSV, TSV, human-readable tables).

## Development Commands

```bash
make install                              # Install dependencies
make run CMD="activities list --limit 5"  # Run CLI command
make test                                 # Run all tests
make test/test_cli.py::test_function_name # Run single test
make lint                                 # Check linting
make fmt                                  # Format and auto-fix
make can-release                          # Run all CI checks (lint + test)
```

## Architecture

### Source Layout

```
src/garmin_connect_cli/
├── cli.py           # Main Typer app, global options
├── core.py          # State singleton, @with_client decorator, emit() helper
├── client.py        # GarminClient wrapper with token management via Garth
├── config.py        # XDG-compliant config (TOML), token path helpers
├── output.py        # Output formatters (JSON, JSONL, CSV, TSV, human tables)
└── commands/        # Subcommand modules (each exports a Typer app)
    ├── activities.py
    ├── athlete.py
    ├── auth.py
    ├── context.py
    ├── health.py
    ├── training.py
    └── weight.py
```

### Key Patterns

**Command Structure**: Each command module creates a `typer.Typer()` app and registers commands using `@app.command()`. Commands access global state via `core.state` for format/fields/profile options.

**Client Pattern**: Commands use the `@with_client` decorator from `core.py` to inject an authenticated `GarminClient`. This decorator hides the `client` parameter from Typer's CLI parser and handles authentication automatically:

```python
@app.command("list")
@with_client
def list_activities(client: GarminClient, limit: int = 30) -> None:
    activities = client.get_activities(limit=limit)
    emit(activities)
```

**Output**: garminconnect returns JSON-serializable dicts, no model serialization needed.

**Authentication**: Tokens are stored in `~/.config/garmin-connect-cli/tokens/` (managed by the Garth library). CLI preferences are in `config.toml`. Authentication uses email/password with optional MFA support.

### Testing

Tests mock garminconnect.Garmin at the class boundary. Key fixtures:
- `mock_garminconnect`: Patches `garmin_connect_cli.client.Garmin`
- `authenticated_env`: Creates temp config and mock token files
- `cli_runner`: Typer's CliRunner for testing commands
- `tmp_token_dir`: Creates mock token directory with token files

### Data Units

Metric: distances (m), times (s), speeds (m/s), elevation (m), dates (ISO8601), HR (BPM).

---

## Server (server.py)

FastAPI app (~1760 lines) that backs the iOS companion app and web dashboard.

**Config**
- Port: `8765` (override with `COACH_PORT` env var)
- Required env vars: `COACH_SERVER_TOKEN` (bearer auth), `ANTHROPIC_API_KEY`
- SQLite DB: `~/.config/garmin-connect-cli/garmin.db`
- Exercise catalog: `data/garmin_exercises.json`
- Web UI: served from `static/index.html` at `GET /`

**Key endpoints** (all except `/health` require `Authorization: Bearer <token>`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check (unauthenticated) |
| POST | `/sync` | Pull today's Garmin data into DB |
| GET | `/status` | Body battery, HRV, readiness, sleep |
| GET | `/activities` | Activity history |
| GET | `/plan` | Current training plan JSON |
| GET | `/trends` | Load trends over N days |
| POST | `/coach` | Design + upload workouts via Claude |
| POST | `/evaluate` | Post-workout load analysis |
| POST | `/analyze` | Claude-powered activity analysis |
| POST | `/chat` | Multi-turn coaching chat |
| GET/DELETE | `/conversations/{id}` | Chat history |
| POST | `/remember` | Append fact to athlete context |
| GET | `/context` | Current athlete context |

**Claude integration**: `server.py` calls `anthropic.Anthropic()` directly for dynamic workout design, coaching chat, and activity analysis. Reads `ANTHROPIC_API_KEY` from env.

**Key internal helpers**
- `_load_athlete_context()` — reads athlete context from DB, 30s TTL cache
- `_design_dynamic_workout()` — Claude tool-use to pick exercises from Garmin catalog
- `_build_sessions()` / `_upload_and_schedule()` — workout creation and Garmin upload

**Running locally**
```bash
COACH_SERVER_TOKEN=dev ANTHROPIC_API_KEY=sk-... python server.py
```

---

## Deployment

The server runs on a remote Linux machine accessible via **Tailscale**.

- Deployed path: `/opt/garmin-connect-cli/`
- Systemd service: `garmincoach` (defined in `garmin-coach.service`)
- Env vars injected from: `/etc/garmincoach.env`
- Self-hosted GitHub Actions runner handles deploys

**CI/CD pipeline** (push to `main`):
1. `Test` workflow — lint + tests across Python 3.10–3.13
2. `Deploy Server` workflow — triggered on Test success; pulls, syncs deps, restarts `garmincoach`

Use `/deploy` to push + watch the full pipeline.

---

## iOS Companion

`~/Github/Garmin-Coach` — SwiftUI app that calls this server's REST API over Tailscale. Separate repo.

---

## Skills

| Skill | Purpose |
|-------|---------|
| `/coach [running\|strength\|weekly]` | Design + upload workouts to Garmin Connect |
| `/evaluate` | Post-workout evaluation, load metrics, calendar adjustment |
| `/deploy` | Local gate → push → watch CI → verify server |
| `/fix` | Run `make can-release`, diagnose failures, auto-fix, repeat until green |
| `/status` | Project health dashboard: git, CI, server, today's Garmin snapshot |

---

## Server Health Check

An hourly systemd timer (`garmincoach-healthcheck.timer`) runs on the server and curls
`localhost:8765/health`. If the server doesn't respond, it pushes a notification via
[ntfy.sh](https://ntfy.sh).

**One-time setup** (run on the server after first deploy):
```bash
sudo bash /opt/garmin-connect-cli/setup_healthcheck.sh <your-ntfy-topic>
```

Subscribe to `https://ntfy.sh/<your-ntfy-topic>` in the ntfy app to receive alerts.
`NTFY_TOPIC` is stored in `/etc/garmincoach.env` alongside the other secrets.

The deploy workflow (`deploy-server.yml`) also now curls `localhost:8765/health` after
every restart as an inline verification step.

---

## Known Footguns

These have tripped up past sessions. Do not re-derive — just follow the workaround.

| Gotcha | Symptom | Workaround |
|--------|---------|------------|
| `uv` not on PATH in Claude Code bash | `make install/test/lint/fmt` all fail with `uv: command not found` | Prepend `export PATH="$HOME/.local/bin:$PATH"` to any `make` call, or use `~/.local/bin/uv run` directly |
| Shell Python is 3.9 | `py_compile` gives false `SyntaxError` on `server.py` which uses `match` statements (3.10+) | Don't use `py_compile` for syntax checks. Use `~/.local/bin/uv run python -m py_compile` instead, or just trust the logic review |
| `CLAUDE.md` is a symlink | `Edit` on `CLAUDE.md` is refused with "refusing to write through symlink" | Edit `AGENTS.md` directly — `CLAUDE.md` symlinks to it |
| Server is remote (Tailscale) | `curl localhost:8765` fails; `python server.py` starts a second instance locally | The server runs on `garmincoach-server` over Tailscale. `static/index.html` has no build step — reload browser after edits. Use `/status` to probe the real server |
| `settings.local.json` is not git-tracked | Harness changes there don't deploy; CI runner doesn't have them | Harness config is local-only by design. Document any CI-relevant changes in `AGENTS.md` instead |
| `server.py` not covered by `make test` | Tests pass but server is broken | `make test` only covers `src/garmin_connect_cli/`. Server correctness requires `/deploy` + `/status` health probe |
| Garmin API rate limiting | HTTP 429 on rapid repeated calls | Space API calls; use DB cache via `/sync` instead of live calls where possible |

---

## Autonomy Boundaries

What Claude can do unilaterally vs. what needs human confirmation.

| Zone | Examples | Policy |
|------|----------|--------|
| **Green — act freely** | Edit/create files, run tests, read vault, `make fmt/lint`, read logs, `git status/diff/log`, `gh run list` | No confirmation needed |
| **Yellow — act and announce** | `git commit`, `git push`, `make install`, `gh run watch`, restart local processes | Do it, but tell the user what you did and why |
| **Red — always confirm first** | Force push (`git push --force`), drop or migrate the SQLite DB, edit `/etc/garmincoach.env` on the server, delete any file not created in this session, anything that modifies production data outside the normal CI/deploy pipeline | Stop. Describe what you want to do and why, then wait for approval |

**On ambiguity:** if an action isn't clearly Green, treat it as Yellow. If it's not clearly Yellow, treat it as Red. Err toward confirmation over autonomy when the blast radius is large or the action is irreversible.

**Memory and self-learning:** when you discover a non-obvious fact (an API shape, a deployment quirk, a repeated failure pattern), write it to `.claude/memory/` immediately — don't defer to end of session. Use `failure_scratch.md` for raw failure notes; formalize into named memory files when the pattern is confirmed.
