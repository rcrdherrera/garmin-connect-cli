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

Read these memory files in parallel:

```
Read: C:\Users\ricar\.claude\projects\C--garmin-connect-cli\memory\hr_zones.md
Read: C:\Users\ricar\.claude\projects\C--garmin-connect-cli\memory\race_goals_2026.md
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

Write a Python script to `C:\Users\ricar\AppData\Local\Temp\garmin_evaluate.py` and run it. Use PowerShell to write (`$script | Out-File -FilePath ... -Encoding utf8`) then execute.

```python
import sys, json, math
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\garmin-connect-cli\src")
from garmin_connect_cli.client import GarminClient
from garmin_connect_cli.config import Config
import sqlite3

ACTIVITY_ID = None  # Replace with $ARGUMENTS if provided, else None

config = Config.load()
client = GarminClient(config)
client.ensure_authenticated()

DB = r"C:\Users\ricar\.config\garmin-connect-cli\garmin.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ── 1. Identify target activity ───────────────────────────────────────────────
if ACTIVITY_ID:
    activities = client.get_activities(start=0, limit=20)
    target_act = next((a for a in activities if a["activityId"] == ACTIVITY_ID), None)
else:
    # Most recent run (skip strength sessions)
    activities = client.get_activities(start=0, limit=10)
    target_act = next(
        (a for a in activities
         if a.get("activityType", {}).get("typeKey", "")
         in ("running", "treadmill_running", "track_running")),
        None
    )

if not target_act:
    print(json.dumps({"error": "No recent run found"}))
    sys.exit(0)

aid = target_act["activityId"]
act_date = target_act["startTimeLocal"][:10]

# ── 2. Fetch evaluation (feel + RPE) ─────────────────────────────────────────
evaluation = client.get_activity_evaluation(aid)

# ── 3. Get activity metrics from DB ──────────────────────────────────────────
cur = conn.execute("""
    SELECT distance_m, duration_s, avg_hr, max_hr, avg_cadence,
           aerobic_te, training_load,
           hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s,
           activity_name, activity_type
    FROM activities WHERE activity_id = ?
""", (aid,))
row = cur.fetchone()

if not row:
    print(json.dumps({"error": f"Activity {aid} not in DB — sync may be needed"}))
    sys.exit(0)

total_zone_s = sum(filter(None, [row["hr_z1_s"], row["hr_z2_s"], row["hr_z3_s"], row["hr_z4_s"], row["hr_z5_s"]])) or 1
z2_pct = round((row["hr_z2_s"] or 0) / total_zone_s * 100, 1)
z3_plus_pct = round(((row["hr_z3_s"] or 0) + (row["hr_z4_s"] or 0) + (row["hr_z5_s"] or 0)) / total_zone_s * 100, 1)

activity_info = {
    "activityId": aid,
    "date": act_date,
    "name": row["activity_name"],
    "type": row["activity_type"],
    "distance_km": round((row["distance_m"] or 0) / 1000, 2),
    "duration_min": round((row["duration_s"] or 0) / 60, 1),
    "avg_hr": row["avg_hr"],
    "max_hr": row["max_hr"],
    "avg_cadence": row["avg_cadence"],
    "aerobic_te": row["aerobic_te"],
    "training_load": row["training_load"],
    "hr_z2_pct": z2_pct,
    "hr_z3plus_pct": z3_plus_pct,
}

# ── 4. Compute ACWR (7-day / 28-day) ─────────────────────────────────────────
today = date.today()
day28_ago = (today - timedelta(days=28)).isoformat()
day7_ago  = (today - timedelta(days=7)).isoformat()

cur = conn.execute("""
    SELECT SUM(training_load), COUNT(*)
    FROM activities
    WHERE start_time_local >= ? AND start_time_local < ?
      AND activity_type IN ('running','treadmill_running','track_running')
""", (day28_ago, (today + timedelta(days=1)).isoformat()))
r28 = cur.fetchone()
chronic_load = (r28[0] or 0) / 4  # weekly average of 4-week window

cur = conn.execute("""
    SELECT SUM(training_load)
    FROM activities
    WHERE start_time_local >= ? AND start_time_local < ?
      AND activity_type IN ('running','treadmill_running','track_running')
""", (day7_ago, (today + timedelta(days=1)).isoformat()))
acute_load = cur.fetchone()[0] or 0

acwr = round(acute_load / chronic_load, 2) if chronic_load > 0 else None

# ── 5. Compute CTL / ATL / TSB (Banister) ────────────────────────────────────
# τCTL=42 days, τATL=7 days
cur = conn.execute("""
    SELECT start_time_local[:10] as d, SUM(training_load) as load
    FROM activities
    WHERE start_time_local >= ?
      AND activity_type IN ('running','treadmill_running','track_running',
                            'strength_training','fitness_equipment')
    GROUP BY d ORDER BY d
""", (day28_ago,))

ctl, atl = 0.0, 0.0
k_ctl = math.exp(-1/42)
k_atl = math.exp(-1/7)

last_date = None
for drow in cur.fetchall():
    d = drow[0]
    load = drow[1] or 0
    if last_date:
        gap = (date.fromisoformat(d) - date.fromisoformat(last_date)).days
        for _ in range(gap):
            ctl = ctl * k_ctl
            atl = atl * k_atl
    ctl = ctl * k_ctl + load * (1 - k_ctl)
    atl = atl * k_atl + load * (1 - k_atl)
    last_date = d

tsb = round(ctl - atl, 1)
ctl = round(ctl, 1)
atl = round(atl, 1)

# ── 6. Get morning HRV ────────────────────────────────────────────────────────
try:
    hrv_data = client.get_hrv_data(today.isoformat())
    hrv_summary = hrv_data.get("hrvSummary", {})
    hrv_last = hrv_summary.get("lastNightAvg")
    hrv_weekly = hrv_summary.get("weeklyAvg")
    hrv_status = hrv_summary.get("status")
    hrv_baseline_low = hrv_summary.get("baseline", {}).get("lowUpper") if hrv_summary.get("baseline") else None
    hrv_baseline_high = hrv_summary.get("baseline", {}).get("balancedHigh") if hrv_summary.get("baseline") else None
    hrv_drop_pct = round((hrv_weekly - hrv_last) / hrv_weekly * 100, 1) if hrv_last and hrv_weekly else None
except Exception:
    hrv_last = hrv_weekly = hrv_status = hrv_drop_pct = hrv_baseline_low = hrv_baseline_high = None

conn.close()

result = {
    "activity": activity_info,
    "evaluation": evaluation,
    "load_metrics": {
        "acute_load_7d": round(acute_load, 1),
        "chronic_load_weekly_avg": round(chronic_load, 1),
        "acwr": acwr,
        "ctl": ctl,
        "atl": atl,
        "tsb": tsb,
    },
    "recovery": {
        "hrv_last_night": hrv_last,
        "hrv_weekly_avg": hrv_weekly,
        "hrv_status": hrv_status,
        "hrv_drop_pct": hrv_drop_pct,
        "hrv_baseline_low": hrv_baseline_low,
        "hrv_baseline_high": hrv_baseline_high,
    },
}

print(json.dumps(result, indent=2))
```

Run it:
```powershell
& "C:\garmin-connect-cli\.venv\Scripts\python.exe" "C:\Users\ricar\AppData\Local\Temp\garmin_evaluate.py"
```

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

### 4a — Read the training plan

If `training_plan.json` was found in Step 1, identify:
- The next 1–3 upcoming sessions (date > today)
- Their `garmin_workout_id` and `garmin_scheduled_id`
- Their planned `intensity` (easy / moderate / hard)

### 4b — Execute changes via Python

Write a new script to `C:\Users\ricar\AppData\Local\Temp\garmin_reschedule.py` for any calendar changes needed.

**Pattern for rescheduling:**
```python
from pathlib import Path
import json
from garminconnect import Garmin

TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"
client = Garmin()
client.login(str(TOKEN_DIR))

# Remove old scheduled workout from calendar
client.garth.request("DELETE", "connectapi",
    f"/workout-service/schedule/{scheduled_workout_id}", api=True)

# Schedule replacement workout (must already exist in library)
result = client.garth.post("connectapi",
    f"/workout-service/schedule/{replacement_workout_id}",
    json={"date": "YYYY-MM-DD"}, api=True).json()
print("New scheduled ID:", result.get("scheduledWorkoutId"))
```

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
