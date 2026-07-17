---
description: Post-workout evaluation — reads Garmin self-assessment, computes load metrics, adjusts the upcoming calendar
argument-hint: [activity_id]
allowed-tools: [Read, Write, Bash, PowerShell]
---

# /evaluate — Post-Workout Adaptive Evaluation

You are a running coach and exercise scientist. Your job is to evaluate the most recently completed run against the training plan, compute physiological load metrics, and adjust the upcoming Garmin calendar if the data warrants it.

User invoked with: `$ARGUMENTS` (optional activity ID; if blank, use most recent run)

---

## Step 1 — Load Athlete Context

Read these memory files in parallel (same in-repo set `server.py` and `/coach` read):

```
Read: .claude/memory/hr_zones.md
Read: .claude/memory/race_goals_2026.md
```

Key values to extract:
- Z2 ceiling: 162 bpm (LT1)
- Current phase and phase rules (volume, intensity limits, days since clearance 2026-05-16)
- Cadence target: 168–172 spm

Also read the training plan if it exists:
```
Read: C:\Users\ricar\.config\garmin-connect-cli\training_plan.json
```

---

## Step 2 — Pull Workout Data

DB path: `C:\Users\ricar\.config\garmin-connect-cli\garmin.db`
Python: `C:\Users\ricar\Github\garmin-connect-cli\.venv\Scripts\python.exe`

> **IMPORTANT — DB may be stale.** A just-completed run won't be in the DB until you sync. Always sync first so the target activity and its post-run readiness/HRV are present:
> ```powershell
> uv run python garmin_db.py sync --since <race_or_run_date>
> ```
> (or a plain `uv run python garmin_db.py sync` to backfill from the last-synced date).

### Run the evaluation command

All derived-metric computation — the activity summary (distance/pace/HR/cadence/**HR-zone split**), the load metrics (**ACWR**, and the Banister **CTL/ATL/TSB**), and the recent HRV/readiness recovery rows — lives in `garmin_db.py`'s `evaluate` subcommand. **Do not hand-write a script for any of this** (the ACWR/CTL/ATL/TSB math used to be re-derived inline every invocation — it's now tested code in `garmin_db.py`):

```powershell
uv run python garmin_db.py evaluate --format json
```

- Defaults to the **most recent run** in the DB. Pass `--activity <id>` (from `$ARGUMENTS`) to target a specific activity, or `--date YYYY-MM-DD` to compute load metrics as-of a different day (defaults to the activity's own date).
- Output JSON has three blocks: `activity` (incl. `hr_zone_pct` and `hr_z3plus_pct`), `load_metrics` (`acwr`, `ctl`, `atl`, `tsb`, `acute_load`, `chronic_load_weekly_avg`), and `recovery` (`health_recent`, `readiness_recent`).

### Fetch the subjective self-assessment (feel/RPE)

Feel and RPE are **live-only** — Garmin stores them on the activity, not in the local DB. Fetch them with one client call (this is the only per-invocation Python needed, and it's trivial):

```powershell
uv run python -c "import sys; sys.path.insert(0, r'C:\Users\ricar\Github\garmin-connect-cli\src'); from garmin_connect_cli.client import get_client; c=get_client(); c.ensure_authenticated(); import json; print(json.dumps(c.get_activity_evaluation(<ACTIVITY_ID>)))"
```

`get_activity_evaluation` returns `feel` (0–100 label) and `rpe_10` (0–10). **Both are often `None`** — Ricardo frequently doesn't log them. If null, evaluate on objective data alone (HR/zones/load/HRV) and note that the subjective read was missing.

<details>
<summary>Legacy note — the old inline script (removed)</summary>

Previously this step wrote a ~130-line script to a temp file that re-implemented DB auth, zone math, ACWR and the CTL/ATL/TSB EWMA by hand every run. That logic now lives in `garmin_db.py` (`compute_load_metrics`, `summarize_activity`, `find_latest_run`) with unit-test coverage. If you ever need the raw per-day inputs the old script computed, use `garmin_db.py analyze --since <d> --until <d> --format json` for the activity/health/training `daily_rows`.

</details>

---

## Step 3 — Evaluate the Session

Parse the JSON output and apply the decision rules below. Classify the completed session first, then determine what (if anything) changes in the upcoming plan.

### 3a — Determine session type from the data

Classify the completed run as one of:
- **Easy/Z2**: activity name contains "Easy", "Recovery", "Fácil", or avg_hr ≤ 162 and hr_z3plus_pct < 15%
- **Moderate/Tempo**: avg_hr 163–174, or hr_z3plus_pct 15–40%
- **Hard/Intervals**: avg_hr > 174, or hr_z3plus_pct > 40%, or name contains "Fartlek", "Intervals", "Quality", "Track"

### 3b — Evaluation rules by session type

**If Easy/Z2:**

| Condition | Verdict | Next session action |
|-----------|---------|-------------------|
| avg_hr ≤ 162 AND feel ≥ 75 AND rpe_10 ≤ 3.5 | On target | Keep plan unchanged |
| avg_hr > 162 (5–10 bpm over) OR feel = 50 | Slightly hard | Flag only; keep plan |
| avg_hr > 172 OR feel ≤ 25 OR rpe_10 > 5 | Struggled | Push next hard session back 1 day; insert easy |
| cadence < 165 spm | Cadence alert | Note cue; no plan change |

**If Hard/Intervals:**

| Condition | Verdict | Next session action |
|-----------|---------|-------------------|
| feel ≥ 75 AND rpe_10 ≤ 6 | Controlled effort | 1 mandatory easy day, then resume plan |
| feel = 50 OR rpe_10 6–8 | Taxing | 2 easy days before next hard session |
| feel ≤ 25 OR rpe_10 > 8 | Very hard | Rest or 20min Z1 next day; re-evaluate before next hard |

**ACWR overrides (apply on top of above):**

| ACWR | Action |
|------|--------|
| < 0.8 | Under-training — can consider adding volume next session |
| 0.8–1.3 | Safe zone — no adjustment needed |
| 1.3–1.5 | Caution — reduce next session volume 20% |
| > 1.5 | High risk — replace any upcoming hard session with easy; reduce volume 30% |

**HRV overrides (apply last — highest priority):**

| Condition | Action |
|-----------|--------|
| hrv_status = "LOW" OR hrv_drop_pct > 10 | Force next session to easy/rest regardless of plan |
| hrv_drop_pct 5–10 (moderate suppression) | Drop one intensity tier for next session |
| hrv_status = "BALANCED" | No override |

**TSB signal (context only — don't override ACWR/HRV rules):**

| TSB | Interpretation |
|-----|---------------|
| > +10 | Fresh — good time for quality if HRV/ACWR allow |
| -5 to +10 | Normal training fatigue |
| -20 to -5 | Accumulating — be conservative |
| < -20 | Deep fatigue — prioritize recovery |

### 3c — Phase-specific constraints

Always check current phase before adjusting:
- **Phase 1 (May 16 – Jun 6)**: No Z3+ in any adjusted session. Replace hard sessions with easy Z2 only.
- **Phase 2 (Jun 7 – Jun 27)**: Short Z3 surges (4×30sec) allowed if PTT asymptomatic.
- **Phase 3+**: Normal periodization, but still respect ACWR/HRV gates.

---

## Step 4 — Apply Adjustments to Calendar

If the decision engine determined changes are needed, act on them now.

### 4a — Read the upcoming schedule

The **live Garmin calendar is the source of truth** (`training_plan.json` can be stale). See what's actually scheduled with:

```bash
garmin-connect --format json calendar show --month YYYY-MM
```

One row per day with `workouts` (scheduled) and `activities` (completed). Identify the next 1–3 upcoming sessions (date > today) and their intensity. To get the `workoutId` + scheduled `id` needed to move/replace a session, use `client.get_calendar_month(year, month)` (same data, raw items). `training_plan.json` mirrors this and also carries `garmin_workout_id` / `garmin_scheduled_id` per session — use it as a convenience cache, but reconcile against the calendar if they disagree.

### 4b — Execute changes via Python

Write a short scratch script for any calendar changes needed. **Use the `GarminClient` wrapper — never `garminconnect.Garmin()` directly.** The raw library's schedule response does not parse correctly (it returns `workoutScheduleId`, not `scheduledWorkoutId` — reading the wrong key silently yields `None` on success); the wrapper's `schedule_workout`/`replace_workout` handle this. This is the same rule `/coach` uses.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "GitHub" / "garmin-connect-cli" / "src"))
from garmin_connect_cli.client import get_client

client = get_client()
client.ensure_authenticated()

# Reschedule an existing library workout to a new date:
sched = client.schedule_workout(replacement_workout_id, "YYYY-MM-DD")
print("New scheduled ID:", sched.get("workoutScheduleId"))

# Or swap one already-scheduled session for a freshly-built one in a single call:
# result = client.replace_workout(old_workout_id, old_scheduled_id, new_workout_dict, "YYYY-MM-DD")
# print("workout_id:", result["workout_id"], "scheduled_id:", result["scheduled_id"])
```

To remove a session from the calendar without a replacement, use `client.delete_scheduled_workout(scheduled_workout_id)` (the scheduled-id from the plan, **not** the workout-library id). `client.delete_workout(workout_id)` deletes the library template itself — usually not what you want mid-plan.

**If the replacement session type doesn't exist in the library yet**, build it first using the same workout construction patterns from the `/coach` skill (run_seg, rep_group etc.), upload it, then schedule it.

Easy recovery run template (20–25 min, Z1 only, cadence 168 spm):
```python
easy_steps = [
    run_seg(1, STEP_WARMUP,   300,  "Walk 5min"),
    run_seg(2, STEP_INTERVAL, 1200, "Z1 easy run — HR < 155, cadence 168 spm"),
    run_seg(3, STEP_COOLDOWN, 300,  "Walk 5min"),
]
```

### 4c — Update training_plan.json

After any calendar changes, update the plan file:
```python
PLAN_FILE = Path.home() / ".config" / "garmin-connect-cli" / "training_plan.json"
plan = json.loads(PLAN_FILE.read_text())

# Mark completed session
for s in plan["sessions"]:
    if s["date"] == act_date:
        s["completed"] = True
        s["actual_activity_id"] = aid

# Update any rescheduled sessions
# ... (update garmin_scheduled_id, date, intensity for modified sessions)

PLAN_FILE.write_text(json.dumps(plan, indent=2))
```

---

## Step 5 — Coaching Report

After evaluation (and any calendar changes), give the user a concise report.

### Report format

```
━━━ WORKOUT EVALUATION — [DATE] ━━━

Session: [name] · [distance] km · [duration] min

PERFORMANCE
  HR avg:    [X] bpm  (target ≤ 162)   [✓ On target / ⚠ Over]
  Cadence:   [X] spm  (target 168-172)  [✓ / ⚠]
  Feel:      [feel_label] · RPE [rpe_10]/10
  Load:      [training_load] AU

LOAD METRICS
  ACWR:      [X]   → [Safe / Caution / High risk]
  TSB:       [X]   → [Fresh / Normal / Fatigued / Deep fatigue]
  HRV:       [X] ms ([status], [±X]% vs weekly avg)

VERDICT: [On target / Slightly hard / Struggled / Very taxing]

PLAN ADJUSTMENT: [None — plan unchanged]
  OR
  Next session (Tue May 19): [Easy 25min Z1 → replacing Quality Session]
  Reason: [rpe_10=8.5 + HRV down 9% → 2 easy days required before next hard effort]
  Calendar updated ✓

NEXT 3 DAYS
  Mon May 18: [session name] — [brief note]
  Tue May 19: [adjusted session] — [brief note]
  Wed May 20: [session name] — [brief note]

KEY CUE: [One specific reminder for the next run — e.g. "Cadence was 161 avg — set metronome to 168 before you start"]
```

Keep it short. Numbers first, interpretation after. One clear action the athlete needs to know.

---

## Science Thresholds Reference

- **Z2 ceiling**: 162 bpm (LT1). Easy runs must stay here.
- **Cadence**: 168–172 spm mandatory. Below 165 = overstriding risk.
- **ACWR safe zone**: 0.8–1.3. Above 1.5 = 3–5× injury risk (Gabbett 2016).
- **HRV trigger**: >5% below weekly avg for 2+ days → reduce intensity (Kiviniemi 2007).
- **Post-hard recovery**: minimum 48h before next hard; 72h after RPE ≥ 8 sessions.
- **TSB < −20**: deep fatigue accumulation — recovery priority over fitness gains.
