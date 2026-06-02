---
name: GarminCoach iOS App
description: iOS app project — now backed by a home server (server.py) for full Garmin API access and Claude coaching
type: project
originSessionId: 846d89b3-1a20-4400-a65a-1b1a465010d3
---

iOS coaching app at `/Users/ricardo.herrera/GitHub/Garmin-Coach`.
Home server at `/Users/ricardo.herrera/GitHub/garmin-connect-cli/server.py`.
Deployed on Ubuntu server at `/opt/garmin-connect-cli`.

**Architecture:**

```
iPhone App (Swift/SwiftUI)
    ↓ HTTPS + Bearer token
Home Server (FastAPI, server.py)
    ↓                    ↓
Garmin Connect API    Claude Opus 4.8
    ↓
SQLite garmin.db (historical data + conversation history)
```

**Why home server:** Garmin has no public iOS SDK. The server wraps the existing Python garmin-connect-cli code and calls Claude with the full athlete context. The iOS app just calls the server — it does no data gathering or AI calls itself.

**Server endpoints:**
- `GET /health` — liveness check (no auth)
- `GET /status` — Body Battery, HRV, Readiness, Training Status, Sleep, RHR, Stress (live API + DB fallback for null fields)
- `GET /activities?limit=20` — recent activities
- `GET /plan` — current training_plan.json
- `POST /analyze {"period": "week|month|..."}` — full science-based analysis via Claude; returns `conversation_id`
- `POST /coach {"type": "weekly|running|strength|..."}` — session prescription via Claude; returns `conversation_id`
- `POST /evaluate {"activity_id": null}` — post-run evaluation + plan adjustment via Claude
- `POST /chat {"message", "kind": "ask|coach|analyze", "conversation_id?"}` — multi-turn conversational chat
- `GET /conversations?kind=` — list conversation history
- `GET /conversations/{id}` — full conversation with messages
- `DELETE /conversations/{id}` — delete conversation + messages

**iOS app file structure:**
```
GarminCoach/
├── project.yml                         ← XcodeGen spec (path: GarminCoach scans recursively)
└── GarminCoach/
    ├── App/          GarminCoachApp.swift, ContentView.swift (5 tabs)
    ├── Models/       TrainingModels.swift, CacheManager.swift, Conversation.swift (new)
    ├── Services/     HealthKitManager.swift (unused), ServerClient.swift
    ├── Utilities/    KeychainHelper.swift (stores serverURL + serverToken)
    ├── Views/
    │   ├── Components.swift                    ← MetricCard, ErrorCard, LoadingCard
    │   ├── Components/ConversationHistoryList.swift  ← NEW shared history sheet
    │   ├── ChatView.swift                      ← MessageBubble, TypingIndicator, ConversationThreadView (shared)
    │   ├── CoachingView.swift, AnalyzeView.swift ← now conversational with history
    │   └── StatusView, ChartViews, ActivityListView, EvaluateView, SettingsView
    └── Resources/    Info.plist, GarminCoach.entitlements
```

**App tabs (3 tabs, not 5):**
1. **Today** (StatusView) — live Garmin metrics: Body Battery, HRV, Readiness, Sleep, RHR, Stress
2. **Training** (TrainingView) — activity list grouped by week; Analyze sheet via toolbar button; EvaluateView accessible from activity detail
3. **Coach** (CoachingView) — structured session types (Weekly/Run/Strength/Lower/Upper) + free-chat mode in one view; uses ConversationThreadView for follow-ups
(AnalyzeView opens as a sheet from TrainingView toolbar, not a tab)
(ChatView struct was removed 2026-06-02 as dead code — file still contains shared types: ChatMessage, MessageBubble, TypingIndicator, ConversationThreadView)

**Conversation architecture (2026-05-30):**
- All three AI tabs (Coach, Analyze, Ask) are now multi-turn conversations
- Conversations stored server-side in SQLite (`conversations` + `messages` tables)
- Coach/Analyze: generate the structured brief/report first, then seed the conversation
- Follow-up questions go via `POST /chat {conversation_id, message, kind}`
- History sheet (`ConversationHistoryList`) in each tab's toolbar — swipe to delete
- `ConversationThreadView` (in ChatView.swift) is the shared message list + input bar
- `MessageBubble` renders assistant text via `LocalizedStringKey` for basic markdown

**Settings the user must configure in the app:**
- Server URL: Tailscale IP of home server, e.g. `http://100.x.x.x:8765`
- Server Token: matches `COACH_SERVER_TOKEN` env var on the server

**Design system:** Neo-brutalist WHOOP-inspired. Black background, `Color(white: 0.08)` cards, 1px `Color.white.opacity(0.1)` border, red accent `Color.brutalRed`, all-caps bold labels. Design tokens in `ChartViews.swift` as `Color` extensions.

**Known operational requirements:**
- Must run `xcodegen generate` in Garmin-Coach/ before building in Xcode (project.yml → .xcodeproj)
- HealthKit requires physical iPhone (not simulator)
- Server push to `main` auto-deploys via GitHub Actions self-hosted runner on Ubuntu

**Data flow for widgets:**
- `StatusView` calls `/status` on load/refresh; DB fallback now ensures recovery/sleep/hrv never stays null if SQLite has data
- Charts use `@Query` SwiftData: `[CachedActivity]` and `[DailySnapshot]` — populated by `CacheManager` from `/activities` and `/trends` (1-hour rate-limit on sync)
- Charts show placeholder ("No runs in this period") when empty — NO fake sample data

**Fixed in 2026-05-30:**
- AWAITING DATA: `/status` now backlills from SQLite when live API returns null
- Chart dummy/mock data removed from `WeeklyMileageCard` and `HRZonesAggregateCard`
- Chat 404: trailing-slash fix in `ServerClient.request()`; multi-turn chat with conversation_id
- Coach/Analyze/Ask output: chat bubble format instead of raw text block
- Model bumped to claude-opus-4-8
