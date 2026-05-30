---
name: project-server-setup
description: "GarminCoach FastAPI server infrastructure — Ubuntu deployment, self-hosted runner, DB sync, known bugs fixed"
metadata: 
  node_type: memory
  type: project
  originSessionId: aacc24e8-8221-4c21-851f-796b97e573c8
---

Server is deployed on an Ubuntu machine (`ubuntu-labserver`) at `/opt/garmin-connect-cli`.

**Infrastructure:**
- Service: `garmincoach.service` (systemd) — runs `server.py` via uvicorn
- GitHub Actions self-hosted runner configured via `setup_runner.sh` — any push to `main` on the fork auto-deploys and restarts the service
- Daily DB sync: `garmin-db-sync.service` + `garmin-db-sync.timer` (06:00 daily) — runs `garmin_db.py sync` to keep SQLite populated
- Runner setup script: `setup_runner.sh` — requires a fresh token from GitHub repo Settings → Actions → Runners

**DB sync:** `garmin.db` lives at `~/.config/garmin-connect-cli/garmin.db`. Must be populated for:
- HR zone charts in the iOS app (server `/activities` falls back to live API without zone data if DB empty)
- `/trends` endpoint (SQLite-only, no fallback)
- `/analyze` and `/evaluate` endpoints

**Bugs fixed (2026-05-28):**
- `_readiness()` in server.py was treating `get_training_readiness()` response as a dict — it returns a **list**. Also used wrong field names (`readinessScore` → `score`, `readinessLevel` → `level`, `readinessFeedbackPhrase` → `feedbackShort`). Fixed in both `/status` and `/coach` endpoints.
- `setup_db_sync.sh` had `EnvironmentFile` pointing to `.env` — `garmin_db.py` doesn't need server env vars, only uses Garmin token files. Removed.
- `_try()` in `/status` was silently swallowing all Garmin API exceptions. Now logs errors to stdout and includes `_errors` in response for visibility.

**Runner confirmed working (2026-05-30):** Self-hosted runner registered on `ubuntu-labserver`. Every push to `personal/main` now auto-deploys and restarts `garmincoach.service`. No path filter — any file change triggers deploy.

**Why:** Server is Ubuntu-only — `start_server.ps1` was deleted; `start_server.sh` is the only startup script.

**How to apply:** When debugging server issues, check `journalctl -u garmincoach -n 50`. For DB issues, check `journalctl -u garmin-db-sync`. The `_errors` field in `/status` response now surfaces Garmin API failures.
