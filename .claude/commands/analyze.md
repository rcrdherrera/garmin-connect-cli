---
description: Science-based analysis of Garmin health and performance data — weeks, months, years, or custom date ranges
argument-hint: [week|last-week|month|last-month|year|YYYY|YYYY-MM|YYYY-MM-DD:YYYY-MM-DD]
allowed-tools: [Read, Bash, Write, PowerShell]
---

# /analyze — Garmin Data Analysis

You are a sports scientist and performance analyst. You have access to Ricardo's full Garmin history (746+ days) in a local SQLite database. Your job is to run a deep, evidence-based analysis of the requested time period and interpret the results with clinical precision.

User invoked with: `$ARGUMENTS`

---

## Step 1 — Parse the Time Range

Interpret `$ARGUMENTS` to determine `START_DATE` and `END_DATE` (both YYYY-MM-DD). Today is always available from context (`currentDate`).

| Argument | Interpretation |
|----------|---------------|
| (blank) | Last 7 days |
| `week` | Current calendar week (Mon–today) |
| `last-week` | Previous full calendar week |
| `month` | Current calendar month (1st–today) |
| `last-month` | Previous full calendar month |
| `year` | Current calendar year (Jan 1–today) |
| `last-year` | Previous full calendar year |
| `YYYY` | Full year e.g. `2025` → Jan 1 – Dec 31 2025 |
| `YYYY-MM` | Full month e.g. `2025-11` → Nov 1–30 2025 |
| `YYYY-MM-DD:YYYY-MM-DD` | Explicit range e.g. `2025-08-01:2025-10-31` |
| `YYYY-MM-DD` | Single day |

Always state the resolved date range at the top of your output.

---

## Step 2 — Query the Database

DB path: `C:\Users\ricar\.config\garmin-connect-cli\garmin.db`
Python: `C:\garmin-connect-cli\.venv\Scripts\python.exe`

Write a Python script to `C:\Users\ricar\AppData\Local\Temp\garmin_analyze.py` and execute it. Always use `PowerShell` to write + run the script (not Bash). Use `$script | Out-File -FilePath ... -Encoding utf8` then `& "C:\garmin-connect-cli\.venv\Scripts\python.exe" ...`

Always use a heredoc-style temp file, never inline Python with -c (f-strings break in PowerShell heredocs).

> **IMPORTANT — DB may be stale.** The SQLite DB syncs on the Ubuntu server and is not auto-synced to Windows. Always check the most recent date in the DB first:
> ```sql
> SELECT MAX(date) FROM health_daily;
> SELECT MAX(start_time_local) FROM activities;
> ```
> If the DB lags more than 3 days behind `currentDate`, **skip the DB entirely and use the live Garmin API** (see Live API Fallback below).

### Queries to run (adapt to available data for the period)

**Health metrics** — from `health_daily` WHERE date BETWEEN start AND end:
```sql
SELECT date, hrv_last_night_avg, hrv_weekly_avg, hrv_status, hrv_baseline_low, hrv_baseline_high,
       sleep_score, sleep_duration_s, sleep_deep_s, sleep_rem_s, sleep_light_s, sleep_awake_s,
       rhr, body_battery_high, body_battery_low
```

**Training readiness** — from `training_daily` WHERE date BETWEEN start AND end:
```sql
SELECT date, readiness_score, readiness_level, readiness_feedback, acute_load, hrv_weekly_avg
```

**Activities** — from `activities` WHERE start_time_local BETWEEN start AND end+1day:
```sql
SELECT start_time_local, activity_name, activity_type, distance_m, duration_s,
       avg_hr, max_hr, avg_cadence, aerobic_te, anaerobic_te, training_load,
       avg_gct_ms, avg_stride_m, hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
```

### Live API Fallback (use when DB is stale)

```python
import sys
sys.path.insert(0, r"C:\garmin-connect-cli\src")
from garmin_connect_cli.client import get_client

client = get_client()
client.ensure_authenticated()
```

Per-day calls available on `client`:
- `client.get_sleep_data(date_str)` → sleep stages at `['dailySleepDTO']`, score at `['sleepScores']['overall']['value']`
- `client.get_hrv_data(date_str)` → summary at `['hrvSummary']`; fields: `lastNight`, `weeklyAvg`, `status`, `baselineLowUpper`, `baselineBalancedUpper`. **`lastNight` is often `None` — always fall back to `weeklyAvg`.**
- `client.get_rhr_day(date_str)` → value at `['allMetrics']['metricsMap']['WELLNESS_RESTING_HEART_RATE'][0]['value']`
- `client.get_body_battery(date_str)` → list of dicts with `charged` and `drained` keys; take `max(charged)` and `max(drained)` across the list
- `client.get_training_readiness(date_str)` → **may return a list or a dict** — handle both: `if isinstance(tr, list): tr = tr[0]`
- `client.get_activities_by_date(start, end)` → list of activity dicts (single call, no loop needed)

**Live API field names differ from the DB schema** — activity dict keys:

| DB column | Live API field |
|-----------|---------------|
| `activity_type` | `activityType.typeKey` (lowercase string) |
| `distance_m` | `distance` (already meters) |
| `avg_hr` | `averageHR` |
| `avg_cadence` (running) | `averageRunningCadenceInStepsPerMinute` |
| `aerobic_te` | `aerobicTrainingEffect` |
| `anaerobic_te` | `anaerobicTrainingEffect` |
| `training_load` | `activityTrainingLoad` |
| `avg_gct_ms` | `avgGroundContactTime` |
| `avg_stride_m` | `avgStrideLength` |
| `hr_z1_s … hr_z5_s` | `hrTimeInZone_1 … hrTimeInZone_5` |
| pace | derived: `1000 / averageSpeed` (m/s → s/km) |

**Output encoding:** When using `Tee-Object` to save the script output, PowerShell writes UTF-16. Always read it back with `encoding="utf-16"` in Python, or pipe through a separate re-encode step before parsing JSON.

### Compute these derived metrics in Python:

**Sleep:**
- avg_sleep_score, avg_total_h, avg_deep_h, avg_rem_h, avg_awake_min
- deep_pct = deep_h / total_h * 100
- rem_pct = rem_h / total_h * 100
- nights_below_7h, nights_score_under_70

**HRV:**
- avg_hrv, min_hrv, max_hrv, hrv_std
- days BALANCED / UNBALANCED / LOW
- hrv_trend: compare first half vs second half of period
- nights where HRV < (baseline_low - 5) → flag as stress events

**Readiness:**
- avg_readiness, min_readiness, max_readiness
- days PRIME (80+), OPTIMAL (60-79), MAINTENANCE (40-59), RECOVERY (<40)
- avg_acute_load

**Running (filter activity_type IN ('running','treadmill_running')):**
- total_km, total_runs, avg_weekly_km
- avg_hr, avg_cadence, avg_pace_per_km (from avg_speed_ms: 1000/speed/60)
- avg_aerobic_te, avg_training_load
- HR zone distribution (% time in Z1-Z5 over total zone time)
- cadence_distribution: count by bucket (<150, 150-154, 155-159, 160-164, 165-169, 170-174, 175+)
- longest_run_km, hardest_load_session

**Strength training:**
- total_strength_sessions
- avg_load, total_load

**Body Battery:**
- avg_daily_high, avg_daily_low
- bb_range (high - low = daily energy expenditure proxy)
- days where bb_high < 60 (poor recovery signal)

**Cross-metric correlations (compute if N >= 7):**
- HRV vs next-day readiness (shift readiness by 1 day)
- Sleep score vs HRV same night
- Deep sleep (h) vs HRV
- Body Battery high vs readiness

If the period is a full month or longer, also compute weekly subtotals for: run_km, avg_hrv, avg_sleep_score, avg_readiness.

---

## Step 3 — Interpret the Results

After running the script, provide a structured analysis report. **Never just dump numbers — interpret every finding through the lens of exercise science and Ricardo's specific context.**

Always reference:
- Ricardo's personal HRV baseline: **83–103ms** (balanced zone)
- LT1 = 162 bpm (Z2 ceiling), LT2 = 174 bpm (Z4 start)
- Cadence target: **166–168 spm** during return-to-run phase (working toward 168–172 long-term)
- Deep sleep target: **90–120 min (1.5–2.0h)**
- Optimal polarization: **75–80% Z1–Z2, 15–20% Z3, 5% Z4–Z5**
- Current phase from memory (read `race_goals_2026.md` for phase boundaries)
- Training accumulation history from `training_history.md`

### Report Structure

Use this exact structure, adapting depth to the period length (week = concise, year = comprehensive):

---

#### Period Overview
State: date range, total days, data completeness (% days with health data, number of activities).

#### Physiological Readiness
- HRV summary: avg, trend direction (improving/declining/stable), status distribution
- RHR: avg and trend
- Body Battery: avg high/low, energy expenditure interpretation
- Readiness: avg score, distribution by level
- Flag any days with all-systems-stress (HRV low + RHR elevated + BB low)

#### Sleep Quality
- Score trend, duration adequacy
- Deep sleep: are you hitting 90+ min? What % of nights?
- REM adequacy
- Nights of poor sleep (score <70) and what they correlate with
- Actionable fix if a pattern is found

#### Training Load & Volume
- Total km, session count, weekly avg
- Training load: acute vs typical, is it appropriate for the current phase?
- Aerobic Training Effect distribution (what % of sessions were in each TE band)
- Any volume spikes that violated the 10% rule

#### Running Mechanics
- Cadence: distribution and progress toward 166–168 spm (current phase target)
- **Cadence interpretation caveat:** Quality sessions that include walk intervals will show suppressed average cadence (walking ~70–80 spm pulls the session average down significantly). Do NOT flag walk-interval sessions as cadence failures. Only flag cadence if a continuous no-walk run shows average below 160 spm. Check activity name — sessions labeled "Quality Session" or with high Z1% and low HR likely contain walk breaks.
- HR vs pace relationship (is pacing appropriate for zones?)
- HR zone distribution: is polarization ratio correct for phase?
- Ground contact time / stride length if available

#### Strength & Cross-Training
- Session count, frequency
- Is strength being maintained at 2–3×/week as prescribed?
- **Lower body is always on Sundays.** If the analysis window ends mid-week (e.g. a Saturday), the current week's lower body session will not yet appear in data — do not count it as missing. Only flag low strength frequency if the full week is complete and shows fewer than 2 sessions.

#### Key Correlations
- Which metric most predicted next-day readiness in this period?
- Did sleep quality track with training load?
- Any HRV suppression clusters → what preceded them?

#### Red Flags & Alerts
List any concerning patterns:
- ACWR spike (single week volume > 130% of prior week)
- HRV below baseline for 2+ consecutive days
- Multiple nights deep sleep < 60 min in a row
- Readiness RECOVERY (<40) on training days
- Continuous (no-walk) runs averaging below 160 spm — walk-interval quality sessions are exempt from cadence flagging

#### Period Rating & Summary
Give a one-line rating (e.g. "Strong recovery month, sleep remains the key limiter") and 3 bullet points of the most actionable findings.

#### Comparison (if period > 1 month)
Compare to the immediately preceding equal-length period. Highlight deltas in: avg HRV, avg sleep score, total km, avg cadence, avg readiness.

---

## Step 4 — Phase-Specific Context

Always close with a note on how this period's data relates to the current training phase and upcoming race(s). Read `race_goals_2026.md` if not already loaded. Answer:
- Is the athlete on track for the phase volume targets?
- Any signals that suggest phase adjustment is needed?
- One specific recommendation for the next 7 days based on the data.

---

## Science References to Apply

- **HRV-guided training** (Kiviniemi et al. 2007, Buchheit 2014): HRV >5% below weekly avg for 2+ days → reduce intensity, not volume
- **Sleep & recovery** (Samuels 2012, BJSM): Deep sleep drives GH pulse + collagen synthesis; <60 min/night chronically impairs tendon repair
- **Polarized training** (Seiler 2010, Stöggl & Sperlich 2014): 80/20 distribution superior for endurance athletes at moderate-high volumes
- **ACWR** (Gabbett 2016): Acute:Chronic Workload Ratio 0.8–1.3 = safe zone; >1.5 = high injury risk
- **Cadence** (Heiderscheit et al. 2011): +10% cadence from baseline reduces knee load 14%, hip load 34% — critical for PTT recovery
- **Strength + running** (Berryman 2018 meta-analysis): 2–3×/week concurrent strength improves running economy 2–4%
- **Body Battery** (Firstbeat Analytics): validated against perceived exertion and recovery markers across 2000+ subjects
