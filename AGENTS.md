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
