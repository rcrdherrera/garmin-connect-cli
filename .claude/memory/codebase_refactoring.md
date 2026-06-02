---
name: codebase-refactoring
description: Architecture review and refactoring done 2026-06-02 — what changed in both repos and why
metadata:
  type: project
---

Comprehensive refactor committed on 2026-06-02 to both repos. No behavior changes — quality, performance, and maintainability only.

## garmin-connect-cli (server.py + garmin_db.py)

**`_open_db()` is the single SQLite connection factory.**
`_db()` (raises 503 if DB missing) and all former `_conv_db()` calls both delegate to `_open_db()`. Before: two nearly-identical connection setups. Changing connection settings (WAL, timeouts) now requires one edit.

**`_garmin()` caches the Garmin client by token file mtime.**
Before: created `Garmin()` + called `g.login(token_dir)` on every single API request. Now: module-level `_garmin_cache` tuple; re-creates only when `oauth2_token.json` mtime changes (i.e., after token refresh or re-auth).

**`_load_athlete_context()` caches by mtime.**
Before: read the file on every Claude call (including every loop iteration in the agentic chat loop). Now: module-level `_context_cache`; re-reads only when the file changes (e.g., after `/remember`).

**`RUN_TYPES` and `LOAD_TYPES` are module-level `frozenset` constants.**
Before: `("running", "treadmill_running", "track_running")` hardcoded in 4+ places across server.py and garmin_db.py. SQL queries now use parameterised placeholders. `LOAD_TYPES = RUN_TYPES | {"strength_training", "fitness_equipment"}`.

**Dead pagination loop removed in `sync_activities`.**
Was a `while True: ... break` that always ran exactly one iteration. Dead variables `start_idx` and `batch` also removed.

**Batch commits in `sync_health` and `sync_training`.**
Before: `conn.commit()` after every single day's row — 90 fsyncs for a 90-day backfill. Now: single commit after the full loop. 10-50× faster for history syncs.

**`_HEALTH_COLS` and `_TRAINING_COLS` extracted as module-level lists** — removes the duplication between the INSERT statement and the dict key extraction.

## Garmin-Coach (iOS)

**`HealthKitManager.swift` and `WorkoutSummary`/`AthleteMetrics` in `TrainingModels.swift` cleared.**
Both were dead since all health data flows through the Garmin server. Files kept (Xcode project references them) but emptied to stubs.

**Dead `struct ChatView` removed from `ChatView.swift`** (~280 lines).
Was a standalone chat tab view never added to `ContentView`'s `TabView`. The file still contains the live shared types: `ChatMessage`, `MessageBubble`, `TypingIndicator`, `ConversationThreadView`, and the new `coachSuggestions` constant.

**`coachSuggestions` extracted as a module-level constant.**
Before: identical `private let suggestions = [...]` in both `ChatView` and `CoachingView`. Now: one definition in `ChatView.swift`, `CoachingView` references it directly.

**`DateFormatter` / `ISO8601DateFormatter` / `RelativeDateTimeFormatter` allocations replaced with static singletons.**
Affected: `ServerClient.localDateString` (called on every network request), `CoachingView.formattedDate`, `ConversationHistoryList.relativeDate` (called per cell), `TrainingView.parseDate` (called per activity per render), `TrainingView.weekLabel`.

**`ConversationHistoryList.onDelete` now rolls back on server failure.**
Before: optimistic delete with silent `try?` — item vanished locally but reappeared on next refresh if server delete failed. Now: snapshots `conversations` before removal, restores if any delete fails.

**`CacheManager` error logging.**
Before: empty `catch {}` blocks — impossible to diagnose why cached data wasn't refreshing. Now: `print("[cache] ... failed: ...")`.

**Dead `ChatResponse` struct removed from `ServerClient.swift`.**
Had `let response: String` — wrong shape for the `/chat` endpoint (which returns `{conversation_id, title, message}`). `ChatTurnResponse` was always the correct type used by `sendChat`.

## What was NOT changed (future work if needed)
- `server.py` is still a 1600-line god file — splitting into `db.py`, `garmin.py`, `ai.py`, `routes/` is the next logical step
- Phase/zone constants still hardcoded in `_coach_system()` string — should move to `athlete_context.md`
- `garmin_db.py` sync still called via `subprocess.run` from `server.py` — should be direct function import
- SQLite WAL mode not yet enabled (`PRAGMA journal_mode=WAL` in `_open_db()` would help concurrent reads)
