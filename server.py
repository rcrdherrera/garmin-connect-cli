#!/usr/bin/env python3
"""GarminCoach home server — REST API backend for the iOS app."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from garminconnect import Garmin
from pydantic import BaseModel

from create_workouts import (
    walk_run_protocol,
    z2_easy_run,
    lower_body_hip_glute,
    upper_body_core,
    full_body_posterior_chain,
)

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN_DIR    = Path.home() / ".config" / "garmin-connect-cli" / "tokens"
DB_PATH      = Path.home() / ".config" / "garmin-connect-cli" / "garmin.db"
PLAN_PATH    = Path.home() / ".config" / "garmin-connect-cli" / "training_plan.json"
MEMORY_DIR   = Path.home() / ".claude" / "projects" / "C--garmin-connect-cli" / "memory"
SERVER_TOKEN = os.environ.get("COACH_SERVER_TOKEN", "")
PORT         = int(os.environ.get("COACH_PORT", "8765"))

if not SERVER_TOKEN:
    raise RuntimeError("COACH_SERVER_TOKEN environment variable must be set before starting the server")

# ── Anthropic client ──────────────────────────────────────────────────────────
_claude = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

# ── Athlete context (loaded once at startup) ──────────────────────────────────
_athlete_context: str = ""


def _load_athlete_context() -> str:
    files = ["training_history.md", "hr_zones.md", "race_goals_2026.md"]
    parts = []
    for fname in files:
        p = MEMORY_DIR / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _athlete_context
    _athlete_context = _load_athlete_context()
    print(f"Athlete context loaded ({len(_athlete_context)} chars)")
    yield


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="GarminCoach", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Auth dependency ───────────────────────────────────────────────────────────
def _auth(authorization: str = Header(default="")):
    if authorization != f"Bearer {SERVER_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid or missing token")


AUTH = Depends(_auth)


# ── Garmin factory ────────────────────────────────────────────────────────────
def _garmin() -> Garmin:
    if not (TOKEN_DIR / "oauth2_token.json").exists():
        raise HTTPException(
            status_code=503,
            detail="Garmin not authenticated — run 'garmin-connect auth login' first",
        )
    g = Garmin()
    g.login(str(TOKEN_DIR))
    return g


# ── DB helper ─────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Garmin database not found")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ── Claude helper ─────────────────────────────────────────────────────────────
def _ask_claude(system: str, prompt: str, max_tokens: int = 2048) -> str:
    resp = _claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _coach_system() -> str:
    return f"""You are a world-class running coach and sports scientist. Athlete permanent context:

{_athlete_context}

Today: {date.today().isoformat()}

Always apply:
- Readiness gate: PRIME (80-100) | OPTIMAL (60-79) | MAINTENANCE (40-59) | RECOVERY (<40)
- HRV override: status=LOW or >10% drop below weekly avg → recovery only regardless of readiness
- HRV override: 5-10% drop → drop one intensity tier
- Phase 1 (May 16 – Jun 6): no Z3+, running every other day, cadence 168 spm mandatory
- HR zones: Z1 <147, Z2 147-162 (LT1), Z3 163-173, Z4 174-181 (LT2), Z5 182+
- Cadence 168-172 spm on every run — non-negotiable for PTT recovery
- 10% weekly volume increase cap — never exceed even if feeling great"""


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/health")
def health_check():
    """Server liveness — no auth required."""
    return {"status": "ok", "date": date.today().isoformat()}


# ── GET /status ───────────────────────────────────────────────────────────────

@app.get("/status", dependencies=[AUTH])
def get_status():
    """Today's full Garmin snapshot: Body Battery, HRV, readiness, sleep, stress, RHR."""
    g = _garmin()
    today = date.today().isoformat()
    result: dict[str, Any] = {"date": today}

    def _try(key: str, fn):
        try:
            result[key] = fn()
        except Exception:
            result[key] = None

    def _body_battery():
        bb = g.get_body_battery(today)
        if bb and isinstance(bb, list):
            levels = [x["bodyBatteryLevel"] for x in bb if x.get("bodyBatteryLevel") is not None]
            if levels:
                return {"current": levels[-1], "high": max(levels), "low": min(levels)}
        return None

    def _hrv():
        s = (g.get_hrv_data(today) or {}).get("hrvSummary", {})
        baseline = s.get("baseline") or {}
        return {
            "last_night": s.get("lastNightAvg"),
            "weekly_avg": s.get("weeklyAvg"),
            "status": s.get("status"),
            "baseline_low": baseline.get("lowUpper"),
            "baseline_high": baseline.get("balancedHigh"),
        }

    def _readiness():
        r = g.get_training_readiness(today) or {}
        return {
            "score": r.get("readinessScore"),
            "level": r.get("readinessLevel"),
            "feedback": r.get("readinessFeedbackPhrase"),
        }

    def _sleep():
        s = g.get_sleep_data(today) or {}
        dto = s.get("dailySleepDTO") or {}
        total = dto.get("sleepTimeSeconds") or 0
        scores = dto.get("sleepScores") or {}
        return {
            "score": scores.get("totalScore"),
            "duration_h": round(total / 3600, 1),
            "deep_h": round((dto.get("deepSleepSeconds") or 0) / 3600, 1),
            "rem_h": round((dto.get("remSleepSeconds") or 0) / 3600, 1),
        }

    _try("body_battery", _body_battery)
    _try("hrv", _hrv)
    _try("readiness", _readiness)
    _try("training_status", lambda: (g.get_training_status(today) or {}).get("trainingStatusPhrase"))
    _try("sleep", _sleep)
    _try("rhr", lambda: (g.get_heart_rates(today) or {}).get("restingHeartRate"))
    _try("stress", lambda: (g.get_stress_data(today) or {}).get("overallStressLevel"))

    return result


# ── GET /activities ───────────────────────────────────────────────────────────

@app.get("/activities", dependencies=[AUTH])
def get_activities(limit: int = 20):
    """Recent activities list."""
    g = _garmin()
    acts = g.get_activities(start=0, limit=limit)
    return [
        {
            "activityId": a.get("activityId"),
            "name": a.get("activityName"),
            "type": (
                a.get("activityType", {}).get("typeKey")
                if isinstance(a.get("activityType"), dict)
                else a.get("activityType")
            ),
            "distance_km": round((a.get("distance") or 0) / 1000, 2),
            "duration_min": round((a.get("duration") or 0) / 60, 1),
            "startTimeLocal": a.get("startTimeLocal"),
            "averageHR": a.get("averageHR"),
            "calories": a.get("calories"),
            "elevationGain": a.get("elevationGain"),
        }
        for a in acts
    ]


# ── GET /plan ─────────────────────────────────────────────────────────────────

@app.get("/plan", dependencies=[AUTH])
def get_plan():
    """Current training plan (training_plan.json)."""
    if not PLAN_PATH.exists():
        return {"plan": None}
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


# ── POST /analyze ─────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    period: str = "week"
    # Accepts: week, last-week, month, last-month, year,
    #          YYYY, YYYY-MM, YYYY-MM-DD:YYYY-MM-DD, YYYY-MM-DD


def _resolve_period(period: str) -> tuple[str, str]:
    today = date.today()
    match period:
        case "week":
            return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
        case "last-week":
            end = today - timedelta(days=today.weekday() + 1)
            return (end - timedelta(days=6)).isoformat(), end.isoformat()
        case "month":
            return date(today.year, today.month, 1).isoformat(), today.isoformat()
        case "last-month":
            first_this = date(today.year, today.month, 1)
            last_prev = first_this - timedelta(days=1)
            return date(last_prev.year, last_prev.month, 1).isoformat(), last_prev.isoformat()
        case "year":
            return date(today.year, 1, 1).isoformat(), today.isoformat()
        case _:
            if ":" in period:
                s, e = period.split(":", 1)
                return s, e
            if len(period) == 7:  # YYYY-MM
                import calendar
                y, m = int(period[:4]), int(period[5:])
                return f"{period}-01", f"{period}-{calendar.monthrange(y, m)[1]:02d}"
            if len(period) == 4:  # YYYY
                return f"{period}-01-01", f"{period}-12-31"
            return period, period  # single day


@app.post("/analyze", dependencies=[AUTH])
def analyze(req: AnalyzeRequest):
    """Science-based analysis of a training period using the SQLite DB."""
    start, end = _resolve_period(req.period)
    conn = _db()

    health = _rows(conn.execute("""
        SELECT date, hrv_last_night_avg, hrv_weekly_avg, hrv_status,
               sleep_score, sleep_duration_s, sleep_deep_s, sleep_rem_s,
               rhr, body_battery_high, body_battery_low
        FROM health_daily WHERE date BETWEEN ? AND ? ORDER BY date
    """, (start, end)).fetchall())

    training = _rows(conn.execute("""
        SELECT date, readiness_score, readiness_level, readiness_feedback, acute_load
        FROM training_daily WHERE date BETWEEN ? AND ? ORDER BY date
    """, (start, end)).fetchall())

    activities = _rows(conn.execute("""
        SELECT start_time_local, activity_name, activity_type,
               distance_m, duration_s, avg_hr, max_hr, avg_cadence,
               aerobic_te, training_load,
               hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
        FROM activities
        WHERE start_time_local BETWEEN ? AND ?
        ORDER BY start_time_local DESC
    """, (f"{start}T00:00:00", f"{end}T23:59:59")).fetchall())

    conn.close()

    system = f"""You are a sports scientist and performance analyst.

{_athlete_context}

Today: {date.today().isoformat()}

Interpret data against Ricardo's specific context: PTT injury history, current phase, race goals,
HRV baseline 83-103ms, LT1=162bpm, LT2=174bpm, cadence target 168-172spm.
Apply Kiviniemi HRV protocol, Gabbett ACWR, Seiler polarization, Heiderscheit cadence research."""

    prompt = f"""Analyze training period: {start} to {end}

HEALTH (daily):
{json.dumps(health, indent=2)}

TRAINING READINESS (daily):
{json.dumps(training, indent=2)}

ACTIVITIES:
{json.dumps(activities, indent=2)}

Provide a complete structured analysis:
- Period Overview (data completeness, total days)
- Physiological Readiness (HRV trend, RHR, Body Battery, Readiness distribution)
- Sleep Quality (score trend, deep sleep adequacy, REM)
- Training Load & Volume (km, weekly avg, zone distribution, ACWR context)
- Running Mechanics (cadence distribution, pace/HR relationship)
- Red Flags & Alerts (anything violating phase rules, injury risk signals)
- Period Rating (one line) + 3 most actionable findings
- Phase context: is the athlete on track? One specific recommendation for next 7 days"""

    return {
        "period": f"{start} to {end}",
        "report": _ask_claude(system, prompt, max_tokens=2048),
    }


# ── POST /coach ───────────────────────────────────────────────────────────────

class CoachRequest(BaseModel):
    type: str = "weekly"
    upload: bool = False
    # type accepts: running | strength | lower-body | upper-body | full-body | weekly


# ── Workout upload helpers ─────────────────────────────────────────────────────

def _build_sessions(session_type: str, readiness: int | None, today: date) -> list[tuple[dict, date]]:
    """Return list of (workout_dict, target_date) pairs based on session type."""
    run_fn = walk_run_protocol if (readiness is not None and readiness < 60) else z2_easy_run
    strength_rotation = [lower_body_hip_glute, upper_body_core, full_body_posterior_chain]

    if session_type == "running":
        return [(run_fn(), today)]
    if session_type == "lower-body":
        return [(lower_body_hip_glute(), today)]
    if session_type == "upper-body":
        return [(upper_body_core(), today)]
    if session_type in ("full-body", "strength"):
        return [(full_body_posterior_chain(), today)]
    if session_type == "weekly":
        # Phase 1 pattern over next 7 days: Run / Strength / Run / Strength / Run / Strength / Rest
        pattern = ["run", "strength", "run", "strength", "run", "strength", "rest"]
        sessions: list[tuple[dict, date]] = []
        strength_idx = 0
        for i, day_type in enumerate(pattern):
            target = today + timedelta(days=i)
            if day_type == "run":
                sessions.append((run_fn(), target))
            elif day_type == "strength":
                sessions.append((strength_rotation[strength_idx % 3](), target))
                strength_idx += 1
        return sessions
    return []


def _upload_and_schedule(g: Garmin, sessions: list[tuple[dict, date]]) -> list[dict]:
    """Upload each workout to Garmin library and schedule it. Returns result list."""
    results = []
    for workout_dict, target_date in sessions:
        entry: dict[str, Any] = {
            "name": workout_dict.get("workoutName", "Unknown"),
            "date": target_date.isoformat(),
        }
        try:
            upload_result = g.upload_workout(workout_dict)
            workout_id = upload_result.get("workoutId")
            sched = g.garth.post(
                "connectapi",
                f"/workout-service/schedule/{workout_id}",
                json={"date": target_date.isoformat()},
                api=True,
            ).json()
            entry["workout_id"] = workout_id
            entry["scheduled_id"] = sched.get("scheduledWorkoutId")
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)
    return results


def _save_training_plan(uploaded: list[dict], today: date) -> None:
    """Write training_plan.json with the uploaded session schedule."""
    week_start = today - timedelta(days=today.weekday())
    plan = {
        "plan_version": 1,
        "created_at": today.isoformat(),
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "sessions": [
            {
                "date": w["date"],
                "name": w["name"],
                "garmin_workout_id": w.get("workout_id"),
                "garmin_scheduled_id": w.get("scheduled_id"),
                "error": w.get("error"),
                "completed": False,
                "actual_activity_id": None,
            }
            for w in uploaded
        ],
    }
    PLAN_PATH.write_text(json.dumps(plan, indent=2))


@app.post("/coach", dependencies=[AUTH])
def coach(req: CoachRequest):
    """Design today's session or a full weekly plan based on live readiness."""
    g = _garmin()
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    live: dict[str, Any] = {}

    def _try(key: str, fn):
        try:
            live[key] = fn()
        except Exception:
            live[key] = None

    def _readiness():
        r = g.get_training_readiness(today) or {}
        return {"score": r.get("readinessScore"), "level": r.get("readinessLevel")}

    def _hrv():
        s = (g.get_hrv_data(today) or {}).get("hrvSummary", {})
        return {
            "last_night": s.get("lastNightAvg"),
            "weekly_avg": s.get("weeklyAvg"),
            "status": s.get("status"),
        }

    def _recent():
        acts = g.get_activities(start=0, limit=20)
        return [
            {
                "name": a.get("activityName"),
                "type": (
                    a.get("activityType", {}).get("typeKey")
                    if isinstance(a.get("activityType"), dict)
                    else a.get("activityType")
                ),
                "date": (a.get("startTimeLocal") or "")[:10],
                "distance_km": round((a.get("distance") or 0) / 1000, 2),
                "duration_min": round((a.get("duration") or 0) / 60, 1),
                "avg_hr": a.get("averageHR"),
            }
            for a in acts
            if (a.get("startTimeLocal") or "") >= week_ago
        ]

    _try("readiness", _readiness)
    _try("hrv", _hrv)
    _try("training_status", lambda: (g.get_training_status(today) or {}).get("trainingStatusPhrase"))
    _try("recent_activities", _recent)

    # Upload workouts before generating the brief so Claude knows exactly what was scheduled
    uploaded: list[dict] = []
    if req.upload:
        readiness_score = (live.get("readiness") or {}).get("score")
        sessions = _build_sessions(req.type, readiness_score, date.today())
        uploaded = _upload_and_schedule(g, sessions)
        _save_training_plan(uploaded, date.today())

    upload_context = ""
    if uploaded:
        lines = [f"  - {w['name']} → {w['date']}" + (f" [ERROR: {w['error']}]" if w.get("error") else " ✓ uploaded & scheduled") for w in uploaded]
        upload_context = f"\n\nWORKOUTS UPLOADED TO GARMIN:\n" + "\n".join(lines) + "\n\nReference these exact workouts in your brief — they are already on the athlete's calendar."

    prompt = f"""Design a {req.type} training session/plan for today ({today}).

TODAY'S PHYSIOLOGICAL STATE:
{json.dumps(live, indent=2)}{upload_context}

1. Interpret readiness score + HRV — apply gate and override rules
2. State current phase and what it allows/forbids today
3. {"Describe the uploaded sessions in detail: structure, HR targets, cadence cues, when to do each" if uploaded else "Design the session(s) with full detail: duration, structure, HR targets, cadence cues"}
4. Key cues the athlete must know before starting
5. Red flags: when to stop or pull back

Be specific and practical. Coach talk, not textbook."""

    return {
        "date": today,
        "type": req.type,
        "brief": _ask_claude(_coach_system(), prompt, max_tokens=2048),
        "uploaded_workouts": uploaded,
    }


# ── POST /evaluate ────────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    activity_id: int | None = None


@app.post("/evaluate", dependencies=[AUTH])
def evaluate(req: EvaluateRequest):
    """Evaluate the most recent run against the plan and recommend adjustments."""
    g = _garmin()
    today = date.today()
    run_types = ("running", "treadmill_running", "track_running")

    acts = g.get_activities(start=0, limit=10)
    if req.activity_id:
        target = next((a for a in acts if a["activityId"] == req.activity_id), None)
    else:
        target = next(
            (
                a for a in acts
                if (
                    a.get("activityType", {}).get("typeKey", "")
                    if isinstance(a.get("activityType"), dict)
                    else a.get("activityType", "")
                ) in run_types
            ),
            None,
        )

    if not target:
        raise HTTPException(status_code=404, detail="No recent run found")

    aid = target["activityId"]
    act_date = target["startTimeLocal"][:10]

    # Garmin self-assessment
    evaluation: dict[str, Any] = {}
    try:
        full = g.get_activity(aid)
        summary = full.get("summaryDTO") or {}
        raw_feel = summary.get("directWorkoutFeel")
        raw_rpe = summary.get("directWorkoutRpe")
        feel_map = {0: "terrible", 25: "weak", 50: "normal", 75: "good", 100: "excellent"}
        evaluation = {
            "feel": feel_map.get(raw_feel) if raw_feel is not None else None,
            "rpe_10": round(raw_rpe / 10, 1) if raw_rpe is not None else None,
        }
    except Exception:
        pass

    # DB activity details
    conn = _db()
    row = conn.execute("""
        SELECT distance_m, duration_s, avg_hr, max_hr, avg_cadence,
               aerobic_te, training_load,
               hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s, activity_name
        FROM activities WHERE activity_id = ?
    """, (aid,)).fetchone()

    activity_info: dict[str, Any] = {"activityId": aid, "date": act_date}
    if row:
        total_z = (
            sum(filter(None, [row["hr_z1_s"], row["hr_z2_s"], row["hr_z3_s"], row["hr_z4_s"], row["hr_z5_s"]]))
            or 1
        )
        activity_info.update({
            "name": row["activity_name"],
            "distance_km": round((row["distance_m"] or 0) / 1000, 2),
            "duration_min": round((row["duration_s"] or 0) / 60, 1),
            "avg_hr": row["avg_hr"],
            "max_hr": row["max_hr"],
            "avg_cadence": row["avg_cadence"],
            "aerobic_te": row["aerobic_te"],
            "training_load": row["training_load"],
            "hr_z2_pct": round(((row["hr_z2_s"] or 0) / total_z) * 100, 1),
            "hr_z3plus_pct": round(
                ((row["hr_z3_s"] or 0) + (row["hr_z4_s"] or 0) + (row["hr_z5_s"] or 0)) / total_z * 100, 1
            ),
        })

    # ACWR
    d28 = (today - timedelta(days=28)).isoformat() + "T00:00:00"
    d7  = (today - timedelta(days=7)).isoformat()  + "T00:00:00"
    r28 = conn.execute(
        "SELECT COALESCE(SUM(training_load),0) FROM activities WHERE start_time_local >= ? AND activity_type IN ('running','treadmill_running','track_running')",
        (d28,),
    ).fetchone()[0]
    r7 = conn.execute(
        "SELECT COALESCE(SUM(training_load),0) FROM activities WHERE start_time_local >= ? AND activity_type IN ('running','treadmill_running','track_running')",
        (d7,),
    ).fetchone()[0]
    chronic = r28 / 4
    acwr = round(r7 / chronic, 2) if chronic > 0 else None

    # CTL / ATL / TSB
    load_rows = conn.execute("""
        SELECT substr(start_time_local,1,10) d, SUM(training_load) load
        FROM activities WHERE start_time_local >= ?
          AND activity_type IN ('running','treadmill_running','track_running','strength_training','fitness_equipment')
        GROUP BY d ORDER BY d
    """, (d28,)).fetchall()
    conn.close()

    ctl, atl = 0.0, 0.0
    k_ctl, k_atl = math.exp(-1 / 42), math.exp(-1 / 7)
    last_d = None
    for r in load_rows:
        d, load = r[0], r[1] or 0
        if last_d:
            for _ in range((date.fromisoformat(d) - date.fromisoformat(last_d)).days):
                ctl *= k_ctl
                atl *= k_atl
        ctl = ctl * k_ctl + load * (1 - k_ctl)
        atl = atl * k_atl + load * (1 - k_atl)
        last_d = d

    # HRV today
    hrv_info: dict[str, Any] = {}
    try:
        s = (g.get_hrv_data(today.isoformat()) or {}).get("hrvSummary", {})
        hrv_info = {
            "last_night": s.get("lastNightAvg"),
            "weekly_avg": s.get("weeklyAvg"),
            "status": s.get("status"),
        }
    except Exception:
        pass

    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8")) if PLAN_PATH.exists() else None
    metrics = {
        "acwr": acwr,
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(ctl - atl, 1),
        "acute_load_7d": round(r7, 1),
        "chronic_weekly_avg": round(chronic, 1),
    }

    prompt = f"""Evaluate this completed run.

ACTIVITY:
{json.dumps(activity_info, indent=2)}

SELF-ASSESSMENT:
{json.dumps(evaluation, indent=2)}

LOAD METRICS:
{json.dumps(metrics, indent=2)}

HRV TODAY:
{json.dumps(hrv_info, indent=2)}

TRAINING PLAN:
{json.dumps(plan, indent=2) if plan else "No plan on file."}

Evaluate using:
1. Classify session (Easy/Z2, Moderate, Hard)
2. Performance vs targets (HR ≤162, cadence 168-172, feel/RPE)
3. ACWR risk zone + recommended action
4. HRV override (if applicable)
5. Phase constraints
6. Plan adjustment decision

Use this report format:
━━━ WORKOUT EVALUATION — {act_date} ━━━

Session: [name] · [distance] km · [duration] min

PERFORMANCE
  HR avg:   [X] bpm  (target ≤162)
  Cadence:  [X] spm  (target 168-172)
  Feel:     [feel] · RPE [rpe]/10
  Load:     [training_load] AU

LOAD METRICS
  ACWR:  [X] → [Safe / Caution / High risk]
  TSB:   [X] → [Fresh / Normal / Fatigued]
  HRV:   [X] ms ([status])

VERDICT: [On target / Slightly hard / Struggled / Very taxing]

PLAN ADJUSTMENT: [None] or [what changes and why]

NEXT 3 DAYS
  [date]: [session]
  [date]: [session]
  [date]: [session]

KEY CUE: [one specific thing to focus on next run]"""

    return {
        "activity_id": aid,
        "date": act_date,
        "metrics": metrics,
        "report": _ask_claude(_coach_system(), prompt, max_tokens=1024),
    }


# ── POST /chat ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/chat", dependencies=[AUTH])
def chat(req: ChatRequest):
    """Free-form coaching chat — ask your AI coach anything."""
    today = date.today().isoformat()

    # Best-effort live metrics for context
    live_context = ""
    try:
        g = _garmin()
        live: dict[str, Any] = {}
        try:
            r = g.get_training_readiness(today) or {}
            live["readiness"] = {"score": r.get("readinessScore"), "level": r.get("readinessLevel")}
        except Exception:
            pass
        try:
            s = (g.get_hrv_data(today) or {}).get("hrvSummary", {})
            live["hrv"] = {
                "last_night": s.get("lastNightAvg"),
                "weekly_avg": s.get("weeklyAvg"),
                "status": s.get("status"),
            }
        except Exception:
            pass
        try:
            live["rhr"] = (g.get_heart_rates(today) or {}).get("restingHeartRate")
        except Exception:
            pass
        try:
            bb = g.get_body_battery(today)
            if bb and isinstance(bb, list):
                levels = [x["bodyBatteryLevel"] for x in bb if x.get("bodyBatteryLevel") is not None]
                if levels:
                    live["body_battery"] = levels[-1]
        except Exception:
            pass
        if live:
            live_context = f"\n\nTODAY'S METRICS:\n{json.dumps(live, indent=2)}"
    except Exception:
        pass

    system = f"""You are a world-class running coach and sports scientist. Athlete context:

{_athlete_context}

Today: {today}{live_context}

You have deep knowledge of evidence-based training principles (Seiler polarization, Lydiard, Maffetone),
injury prevention and return-to-run protocols, HRV interpretation (Kiviniemi protocol), running
biomechanics, nutrition for endurance athletes, and periodization.

Be direct and practical — this is a coach-athlete conversation, not a textbook.
Keep answers focused and actionable. Use clear structure when helpful."""

    resp = _claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": req.message}],
    )
    return {"response": resp.content[0].text}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("COACH_HOST", "127.0.0.1")
    uvicorn.run("server:app", host=host, port=PORT, reload=False)
