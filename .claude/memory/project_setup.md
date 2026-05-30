---
name: Garmin data access setup
description: Two-path setup for Garmin data access — CLI and MCP+Docker, both previously blocked by 429 rate limit; now working
type: project
originSessionId: 54b17310-a221-4d30-b167-3f3f72cd5d07
---
Two parallel paths set up for Garmin Connect data access:

**Path 1 — CLI (primary)**
- Repo: C:\garmin-connect-cli (github.com/eddmann/garmin-connect-cli)
- Runtime: uv v0.11.8, `uv run garmin-connect` works
- Auth: **WORKING** as of 2026-05-03 via browser_auth.py workaround
- Token storage: C:\Users\ricar\.config\garmin-connect-cli\tokens\
- **OAuth2 refresh token expires 2026-06-02** — re-run browser_auth.py before that date or CLI will fail with auth errors
- If tokens expire or 429 recurs: use browser_auth.py (C:\garmin-connect-cli\browser_auth.py)
  - Log into connect.garmin.com in browser, open DevTools → Application → Cookies → sso.garmin.com
  - Copy CASTGC cookie (plus others if present), run `uv run python browser_auth.py`, paste cookies
  - Uses CAS TGT flow: GET /sso/login redirect with CASTGC → ticket → OAuth tokens, no rate-limited POST

**Path 2 — MCP + Claude Desktop**
- Docker image: ghcr.io/eddmann/garmin-connect-mcp:latest (pulled)
- Credentials: C:\garmin-mcp\garmin-connect-mcp.env (GARMIN_EMAIL + GARMIN_PASSWORD)
- Token folder: C:\garmin-mcp\tokens
- Claude Desktop config at %APPDATA%\Claude\claude_desktop_config.json already updated

**Why:** User wants to analyze running/health data with Claude for evidence-based coaching.

**Key CLI commands:**
- `uv run garmin-connect context` — aggregated LLM context (profile + stats + health + training + activities)
- `uv run garmin-connect activities list --after YYYY-MM-DD --activity-type running --limit 200`
- `uv run garmin-connect activities get <id>` — full activity detail including summaryDTO (cadence, GCT, stride, etc.)
- `uv run garmin-connect training hrv --date-str YYYY-MM-DD` — HRV (field: hrvSummary.lastNightAvg, NOT lastNight)
- `uv run garmin-connect health sleep --date-str YYYY-MM-DD`
- `uv run garmin-connect weight list --start YYYY-MM-DD --end YYYY-MM-DD`
- `uv run garmin-connect health rhr --date-str YYYY-MM-DD`

**Adaptive training loop (added 2026-05-17):**
- `garmin-connect workouts list/schedule/unschedule/evaluation` — new CLI subcommand
- `client.schedule_workout(workout_id, date_str)` — POST to `/workout-service/schedule/{id}`
- `client.delete_scheduled_workout(scheduled_id)` — DELETE same endpoint
- `client.get_activity_evaluation(activity_id)` — reads `summaryDTO.directWorkoutFeel` (0=terrible, 50=normal, 75=good, 100=excellent) and `summaryDTO.directWorkoutRpe` (0–100 scale)
- `/evaluate` skill — reads feel/RPE + HR zones + HRV, computes ACWR/CTL/ATL/TSB, adjusts Garmin calendar
- `/coach weekly` now schedules workouts to calendar and saves plan to `~/.config/garmin-connect-cli/training_plan.json`
- Git remote: `personal` → github.com/rcrdherrera/garmin-connect-cli (push here, not origin/eddmann)

**FastAPI server (server.py) — added 2026-05-19, secured 2026-05-27:**
- Runs on an **Ubuntu server** (not Windows) — use `git pull` + manual restart there
- Server restart after push: `git pull personal main && ./start_server.sh` (no auto-restart on push — no git hooks or CI runner wired up)
- `COACH_SERVER_TOKEN` env var is **required** — server raises RuntimeError at startup if missing (fail-closed, not optional)
- Default host binding: `127.0.0.1` — set `COACH_HOST=0.0.0.0` explicitly when iOS app needs LAN access
- Default port: 8765 (override with `COACH_PORT`)
- Endpoints: `/status`, `/activities`, `/analyze`, `/coach`, `/evaluate`, `/chat` (all require Bearer token)

**Known data gaps:**
- VO2max returning null — check Garmin Connect Settings → Physio TrueUp
- Weight: only 2 manual entries (Jul 2025: 76kg, Nov 2025: 79kg) — not consistently tracked
- Hydration: not tracked at all — requires manual logging in Connect app
- HRV: data IS available but field is `lastNightAvg` not `lastNight` (parsing bug fixed)
