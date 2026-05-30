---
name: GarminCoach iOS App
description: iOS app project — now backed by a home server (server.py) for full Garmin API access and Claude coaching
type: project
originSessionId: 846d89b3-1a20-4400-a65a-1b1a465010d3
---

iOS coaching app at `C:\Users\ricar\Github\Garmin-Coach` (GitHub: github.com/rcrdherrera/Garmin-Coach).
Home server at `C:\garmin-connect-cli\server.py`.

**Architecture:**

```
iPhone App (Swift/SwiftUI)
    ↓ HTTPS + Bearer token
Home Server (FastAPI, server.py)
    ↓                    ↓
Garmin Connect API    Claude Opus 4.7
    ↓
SQLite garmin.db (historical data)
```

**Why home server:** Garmin has no public iOS SDK. The server wraps the existing Python garmin-connect-cli code and calls Claude with the full athlete context. The iOS app just calls the server — it does no data gathering or AI calls itself.

**Server endpoints:**
- `GET /health` — liveness check (no auth)
- `GET /status` — Body Battery, HRV, Readiness, Training Status, Sleep, RHR, Stress
- `GET /activities?limit=20` — recent activities
- `GET /plan` — current training_plan.json
- `POST /analyze {"period": "week|month|..."}` — full science-based analysis via Claude
- `POST /coach {"type": "weekly|running|strength|..."}` — session prescription via Claude
- `POST /evaluate {"activity_id": null}` — post-run evaluation + plan adjustment via Claude

**Server setup:**
1. `uv pip install -e ".[server]"` (installs fastapi, uvicorn, anthropic)
2. Edit `start_server.ps1` — set `COACH_SERVER_TOKEN` and `ANTHROPIC_API_KEY`
3. Run `.\start_server.ps1` — listens on port 8765
4. Install Tailscale on home PC + iPhone for remote access

**iOS app file structure:**
```
GarminCoach/
├── project.yml                         ← XcodeGen spec (unchanged)
└── GarminCoach/
    ├── App/          GarminCoachApp.swift, ContentView.swift (5 tabs)
    ├── Models/       TrainingModels.swift
    ├── Services/     HealthKitManager.swift (kept but unused), ServerClient.swift
    ├── Utilities/    KeychainHelper.swift (stores serverURL + serverToken)
    ├── Views/        CoachingView, StatusView, AnalyzeView, EvaluateView, SettingsView
    └── Resources/    Info.plist, GarminCoach.entitlements
```

**App tabs:**
1. **Today** (StatusView) — live Garmin metrics: Body Battery, HRV, Readiness, Sleep, RHR, Stress
2. **Coach** (CoachingView) — session prescription: Weekly/Run/Strength/Lower/Upper
3. **Analyze** (AnalyzeView) — period analysis: This week / Last week / Month / Year
4. **Evaluate** (EvaluateView) — post-run evaluation + plan adjustment
5. **Settings** (SettingsView) — server URL + token, connection test

**Settings the user must configure in the app:**
- Server URL: Tailscale IP of home PC, e.g. `http://100.x.x.x:8765`
- Server Token: matches `COACH_SERVER_TOKEN` in `start_server.ps1`

**Data the server has that HealthKit does NOT:**
- Body Battery, Training Status, Training Readiness, Stress level (Garmin-only)
- Full historical workout data with per-field metrics (SQLite DB)
- ACWR, CTL/ATL/TSB load calculations
- Zone breakdown (hr_z1_s through hr_z5_s)

**Design system (2026-05-28):** Neo-brutalist WHOOP-inspired. Black background, `Color(white: 0.08)` cards, 1px `Color.white.opacity(0.1)` border, red accent `Color(red:1, green:0.12, blue:0.12)`, 10pt corners, all-caps bold labels. Design tokens defined in `ChartViews.swift` as `Color` extensions.

**New charts added (2026-05-28):**
- `WeeklyMileageCard` in `ChartViews.swift` — line+area+point chart, 7D/1M/3M/6M/1Y filter, interactive tooltip via `.chartXSelection`, mock data when CachedActivity empty
- `HRZonesAggregateCard` in `ChartViews.swift` — aggregate HR zones across period, same time filters, BPM range labels, tap-to-highlight interaction, mock distribution when no zone data
- Both charts added to the Today tab (StatusView) below HRV Context card

**Bug fixes (2026-05-28):**
- Recovery shows `--` not `0` when readiness is nil; sleep same fix
- Coach tab: upload toggle removed, replaced by Upload button (disabled until brief shown, upload state machine: idle/uploading/done/failed, shows uploaded workout list with confirmation)
- Chat 404: shows actionable message to restart server
- Analyze/Coach output: em-dash section headers, no emojis (server-side prompt change)

**Current state:** All files written. Not yet compiled — needs Mac + Xcode.
Run `xcodegen generate` in `C:\Users\ricar\Github\Garmin-Coach` to create .xcodeproj.
HealthKit requires physical iPhone for testing (not simulator).

**iOS data flow (confirmed 2026-05-30):**
- `StatusView` calls `ServerClient.shared.getStatus()` → `/status` on load and on refresh button
- Charts use `@Query` SwiftData: `[CachedActivity]` and `[DailySnapshot]`
- `CacheManager.syncActivitiesIfNeeded` and `syncTrendsIfNeeded` have a 1-hour rate limit (interval: 3600) — both silently swallow errors (`catch {}`)
- Activities are reset (rate limit cleared) on app kill; syncs on every fresh launch
- "AWAITING DATA" text is in `RecoveryRingCard` (ChartViews.swift ~line 97) — shows when `status.readiness?.score == nil`
- Charts fall back to mock/sample data when `CachedActivity` empty or no runs in selected period

**Known data issues (2026-05-30):**
- `WeeklyMileageCard` shows mock data if no `isRun` activities in selected period — with Phase 1 limited running, 3M default may appear empty
- `HRZonesAggregateCard` shows sample data if no HR zone data — requires `garmin.db` to be populated (live API fallback has no zone data)
- `/trends` endpoint is SQLite-only (no live API fallback) — returns empty snapshots if DB not synced → no 14-day trend charts
- Daily sync timer (`garmin-db-sync.timer`) set up 2026-05-30 to fix this at 06:00 daily
