#!/usr/bin/env python3
"""GarminCoach home server — REST API backend for the iOS app."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
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
    files = ["training_history.md", "hr_zones.md", "race_goals_2026.md", "home_gym_equipment.md"]
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
    _ensure_conversation_tables()
    print("Conversation tables ready")
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
        model="claude-opus-4-8",
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


# ── Conversation table bootstrap (idempotent) ─────────────────────────────────
def _ensure_conversation_tables() -> None:
    """Create conversations/messages tables if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kind        TEXT NOT NULL,
            title       TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv
            ON messages (conversation_id, id);
        CREATE INDEX IF NOT EXISTS idx_conversations_kind
            ON conversations (kind, updated_at);
    """)
    conn.commit()
    conn.close()


# ── Conversation DB helpers ───────────────────────────────────────────────────
def _conv_db() -> sqlite3.Connection:
    """DB connection that creates the DB + conversation tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _create_conversation(kind: str, title: str) -> int:
    conn = _conv_db()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO conversations (kind, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (kind, title, now, now),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def _add_message(conv_id: int, role: str, content: str) -> dict:
    conn = _conv_db()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, now),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return {"id": mid, "role": role, "content": content, "created_at": now}


def _get_messages(conv_id: int) -> list[dict]:
    conn = _conv_db()
    rows = _rows(conn.execute(
        "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall())
    conn.close()
    return rows


def _touch_conversation(conv_id: int) -> None:
    conn = _conv_db()
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), conv_id),
    )
    conn.commit()
    conn.close()


def _list_conversations(kind: str | None = None) -> list[dict]:
    conn = _conv_db()
    if kind:
        rows = conn.execute(
            "SELECT id, kind, title, created_at, updated_at FROM conversations WHERE kind = ? ORDER BY updated_at DESC",
            (kind,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, kind, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        preview_row = conn.execute(
            "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY id LIMIT 1",
            (d["id"],),
        ).fetchone()
        d["preview"] = preview_row[0][:120] if preview_row else None
        result.append(d)
    conn.close()
    return result


def _get_conversation_detail(conv_id: int) -> dict | None:
    conn = _conv_db()
    row = conn.execute(
        "SELECT id, kind, title, created_at, updated_at FROM conversations WHERE id = ?",
        (conv_id,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    d = dict(row)
    d["messages"] = _rows(conn.execute(
        "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall())
    conn.close()
    return d


def _delete_conversation(conv_id: int) -> bool:
    conn = _conv_db()
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ── Chat context + system helpers ─────────────────────────────────────────────
def _live_context_for_chat() -> str:
    """Best-effort today's live metrics string for chat context ('' on failure)."""
    today = date.today().isoformat()
    try:
        g = _garmin()
        live: dict[str, Any] = {}
        try:
            resp = g.get_training_readiness(today)
            if resp:
                r = resp[0] if isinstance(resp, list) else resp
                live["readiness"] = {
                    "score": r.get("score") or r.get("readinessScore"),
                    "level": r.get("level") or r.get("readinessLevel"),
                }
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
            return f"\n\nTODAY'S METRICS:\n{json.dumps(live, indent=2)}"
    except Exception:
        pass
    return ""


def _system_for_kind(kind: str, live_context: str = "") -> str:
    """Return the appropriate system prompt for coach / analyze / ask conversations."""
    today = date.today().isoformat()
    if kind == "coach":
        return _coach_system()
    if kind == "analyze":
        return f"""You are a sports scientist and performance analyst acting as a running coach.

{_athlete_context}

Today: {today}

Interpret data against Ricardo's specific context: PTT injury history, current phase, race goals,
HRV baseline 83-103ms, LT1=162bpm, LT2=174bpm, cadence target 168-172spm.
Apply Kiviniemi HRV protocol, Gabbett ACWR, Seiler polarization, Heiderscheit cadence research.

Be direct and specific. Use clear structure when helpful. No emojis."""
    # kind == "ask" (default)
    return f"""You are a world-class running coach and sports scientist. Athlete context:

{_athlete_context}

Today: {today}{live_context}

You have deep knowledge of evidence-based training principles (Seiler polarization, Lydiard, Maffetone),
injury prevention and return-to-run protocols, HRV interpretation (Kiviniemi protocol), running
biomechanics, nutrition for endurance athletes, and periodization.

Be direct and practical — this is a coach-athlete conversation, not a textbook.
Keep answers focused and actionable. Use clear structure when helpful."""


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/health")
def health_check():
    """Server liveness — no auth required."""
    return {"status": "ok", "date": date.today().isoformat()}


# ── POST /sync ────────────────────────────────────────────────────────────────

@app.post("/sync", dependencies=[AUTH])
def sync_today():
    """Sync yesterday + today from Garmin Connect into the SQLite DB.

    Called by the iOS app when /status reports stale readiness or sleep data.
    Runs garmin_db.py sync --since <yesterday> in a subprocess and blocks until
    complete (up to 120 s).  Returns the sync result so the app can reload /status.
    """
    since = (date.today() - timedelta(days=1)).isoformat()
    script = REPO_ROOT / "garmin_db.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "sync", "--since", since],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Sync timed out after 120 s")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sync subprocess error: {exc}")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed (exit {result.returncode}): {result.stderr[:300]}",
        )

    return {
        "status": "ok",
        "synced_since": since,
        "output": (result.stdout or "")[-500:],  # last 500 chars for debug
    }


# ── GET /status ───────────────────────────────────────────────────────────────

@app.get("/status", dependencies=[AUTH])
def get_status():
    """Today's full Garmin snapshot: Body Battery, HRV, readiness, sleep, stress, RHR."""
    g = _garmin()
    today = date.today().isoformat()
    result: dict[str, Any] = {"date": today}

    errors: list[str] = []

    def _try(key: str, fn):
        try:
            result[key] = fn()
        except Exception as exc:
            result[key] = None
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

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
        resp = g.get_training_readiness(today)
        if not resp:
            return None
        r = resp[0] if isinstance(resp, list) else resp
        return {
            "score": r.get("score") or r.get("readinessScore"),
            "level": r.get("level") or r.get("readinessLevel"),
            "feedback": r.get("feedbackShort") or r.get("readinessFeedbackPhrase"),
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

    # DB fallback — backfill any field still None / empty from latest SQLite rows
    try:
        if DB_PATH.exists():
            _conn = sqlite3.connect(str(DB_PATH))
            _conn.row_factory = sqlite3.Row
            _h = _conn.execute(
                "SELECT * FROM health_daily ORDER BY date DESC LIMIT 1"
            ).fetchone()
            _t = _conn.execute(
                "SELECT * FROM training_daily ORDER BY date DESC LIMIT 1"
            ).fetchone()
            _conn.close()

            if result.get("readiness") is None and _t:
                result["readiness"] = {
                    "score": _t["readiness_score"],
                    "level": _t["readiness_level"],
                    "feedback": _t["readiness_feedback"],
                }
                result.setdefault("_stale_fields", []).append("readiness")

            _sleep_val = result.get("sleep")
            _sleep_empty = (
                _sleep_val is None
                or (_sleep_val.get("score") is None and (_sleep_val.get("duration_h") or 0) == 0)
            )
            if _sleep_empty and _h:
                result["sleep"] = {
                    "score": _h["sleep_score"],
                    "duration_h": round((_h["sleep_duration_s"] or 0) / 3600, 1),
                    "deep_h": round((_h["sleep_deep_s"] or 0) / 3600, 1),
                    "rem_h": round((_h["sleep_rem_s"] or 0) / 3600, 1),
                }
                result.setdefault("_stale_fields", []).append("sleep")

            _hrv_val = result.get("hrv")
            _hrv_empty = (
                _hrv_val is None
                or (_hrv_val.get("last_night") is None and _hrv_val.get("weekly_avg") is None)
            )
            if _hrv_empty and _h:
                result["hrv"] = {
                    "last_night": _h["hrv_last_night_avg"],
                    "weekly_avg": _h["hrv_weekly_avg"],
                    "status": _h["hrv_status"],
                    "baseline_low": _h["hrv_baseline_low"],
                    "baseline_high": _h["hrv_baseline_high"],
                }
                result.setdefault("_stale_fields", []).append("hrv")

            if result.get("body_battery") is None and _h:
                result["body_battery"] = {
                    "current": None,
                    "high": _h["body_battery_high"],
                    "low": _h["body_battery_low"],
                }
                result.setdefault("_stale_fields", []).append("body_battery")

            if result.get("rhr") is None and _h and _h["rhr"]:
                result["rhr"] = _h["rhr"]
                result.setdefault("_stale_fields", []).append("rhr")
    except Exception as exc:
        errors.append(f"db_fallback: {exc}")

    if errors:
        print(f"[status] {today} — {len(errors)} fetch error(s):")
        for e in errors:
            print(f"  {e}")
        result["_errors"] = errors

    return result


# ── GET /activities ───────────────────────────────────────────────────────────

@app.get("/activities", dependencies=[AUTH])
def get_activities(limit: int = 20):
    """Recent activities with HR zone data — SQLite-first, Garmin API fallback."""
    try:
        conn = _db()
        rows = _rows(conn.execute("""
            SELECT activity_id, activity_name, activity_type,
                   distance_m, duration_s, avg_hr, max_hr, avg_cadence,
                   aerobic_te, training_load, calories, avg_speed_ms,
                   hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s,
                   start_time_local
            FROM activities ORDER BY start_time_local DESC LIMIT ?
        """, (limit,)).fetchall())
        conn.close()
        if rows:
            return [
                {
                    "activityId": r["activity_id"],
                    "name": r["activity_name"],
                    "type": r["activity_type"],
                    "distance_km": round((r["distance_m"] or 0) / 1000, 2),
                    "duration_min": round((r["duration_s"] or 0) / 60, 1),
                    "startTimeLocal": r["start_time_local"],
                    "averageHR": r["avg_hr"],
                    "maxHR": r["max_hr"],
                    "avgCadence": r["avg_cadence"],
                    "calories": r["calories"],
                    "aerobicTE": r["aerobic_te"],
                    "trainingLoad": r["training_load"],
                    "avgSpeedMs": r["avg_speed_ms"],
                    "hrZ1s": r["hr_z1_s"],
                    "hrZ2s": r["hr_z2_s"],
                    "hrZ3s": r["hr_z3_s"],
                    "hrZ4s": r["hr_z4_s"],
                    "hrZ5s": r["hr_z5_s"],
                }
                for r in rows
            ]
    except Exception:
        pass

    # Fallback to live Garmin API (no HR zone data)
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
            "maxHR": None,
            "avgCadence": a.get("averageRunningCadenceInStepsPerMinute"),
            "calories": a.get("calories"),
            "aerobicTE": a.get("aerobicTrainingEffect"),
            "trainingLoad": a.get("activityTrainingLoad"),
            "avgSpeedMs": None,
            "hrZ1s": None, "hrZ2s": None, "hrZ3s": None, "hrZ4s": None, "hrZ5s": None,
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


# ── GET /trends ──────────────────────────────────────────────────────────────

@app.get("/trends", dependencies=[AUTH])
def get_trends(days: int = 30):
    """Historical daily snapshots from SQLite for iOS charting — no live Garmin API call."""
    conn = _db()
    health = _rows(conn.execute("""
        SELECT date, hrv_last_night_avg, hrv_weekly_avg, hrv_status,
               hrv_baseline_low, hrv_baseline_high,
               sleep_score, sleep_duration_s, sleep_deep_s, sleep_rem_s,
               rhr, body_battery_high, body_battery_low
        FROM health_daily ORDER BY date DESC LIMIT ?
    """, (days,)).fetchall())

    training = _rows(conn.execute("""
        SELECT date, readiness_score, readiness_level, acute_load
        FROM training_daily ORDER BY date DESC LIMIT ?
    """, (days,)).fetchall())
    conn.close()

    training_map = {r["date"]: r for r in training}
    snapshots = []
    for h in health:
        d = h["date"]
        t = training_map.get(d, {})
        snapshots.append({
            "date": d,
            "hrv": h.get("hrv_last_night_avg"),
            "hrv_weekly_avg": h.get("hrv_weekly_avg"),
            "hrv_status": h.get("hrv_status"),
            "hrv_baseline_low": h.get("hrv_baseline_low"),
            "hrv_baseline_high": h.get("hrv_baseline_high"),
            "sleep_score": h.get("sleep_score"),
            "sleep_duration_h": round((h.get("sleep_duration_s") or 0) / 3600, 1),
            "sleep_deep_h": round((h.get("sleep_deep_s") or 0) / 3600, 1),
            "sleep_rem_h": round((h.get("sleep_rem_s") or 0) / 3600, 1),
            "rhr": h.get("rhr"),
            "body_battery_high": h.get("body_battery_high"),
            "body_battery_low": h.get("body_battery_low"),
            "readiness_score": t.get("readiness_score"),
            "readiness_level": t.get("readiness_level"),
            "acute_load": t.get("acute_load"),
        })
    snapshots.sort(key=lambda x: x["date"])
    return {"snapshots": snapshots}


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

    if not health and not activities:
        print(f"[analyze] WARNING: no health or activity data found for {start} to {end}")

    system = f"""You are a sports scientist and performance analyst.

{_athlete_context}

Today: {date.today().isoformat()}

Interpret data against Ricardo's specific context: PTT injury history, current phase, race goals,
HRV baseline 83-103ms, LT1=162bpm, LT2=174bpm, cadence target 168-172spm.
Apply Kiviniemi HRV protocol, Gabbett ACWR, Seiler polarization, Heiderscheit cadence research.

FORMAT RULES: No emojis. No bullet-heavy lists. Use em-dash section headers. Be direct and specific.
Write for an athlete who wants honest numbers and clear direction, not encouragement."""

    prompt = f"""Analyze training period: {start} to {end}

HEALTH (daily):
{json.dumps(health, indent=2)}

TRAINING READINESS (daily):
{json.dumps(training, indent=2)}

ACTIVITIES:
{json.dumps(activities, indent=2)}

Use this exact format:

— PERIOD OVERVIEW —
[dates, days with data, data completeness note if gaps exist]

— PHYSIOLOGICAL READINESS —
[HRV trend with numbers, RHR direction, Body Battery pattern, Readiness score distribution]

— SLEEP —
[score trend, duration avg, deep sleep adequacy vs 90-min target, REM]

— TRAINING LOAD & VOLUME —
[total km, weekly avg, zone distribution breakdown, ACWR if calculable]

— RUNNING MECHANICS —
[cadence numbers, pace/HR relationship, phase compliance]

— RED FLAGS —
[anything violating phase rules or signaling injury risk — state "None" if clean]

— VERDICT —
[one sentence period rating]

— NEXT 7 DAYS —
[one specific, concrete recommendation based on this data]"""

    report = _ask_claude(system, prompt, max_tokens=2048)

    # Persist to conversation history
    title = f"Analyze {start} – {end}"
    conv_id = _create_conversation("analyze", title)
    _add_message(conv_id, "user", f"Analyze training period {start} to {end}")
    _add_message(conv_id, "assistant", report)

    return {
        "period": f"{start} to {end}",
        "report": report,
        "conversation_id": conv_id,
        "title": title,
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
        resp = g.get_training_readiness(today)
        if not resp:
            return None
        r = resp[0] if isinstance(resp, list) else resp
        return {"score": r.get("score") or r.get("readinessScore"), "level": r.get("level") or r.get("readinessLevel")}

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

Use this exact format. No emojis. Be direct:

— READINESS GATE —
[score X → gate tier: PRIME/OPTIMAL/MAINTENANCE/RECOVERY. HRV status + any override applied.]

— PHASE STATUS —
[Phase 1 day X of 21. What today allows and what is forbidden.]

— SESSION DESIGN —
[{"Describe each uploaded session: name, full structure, exact HR targets, cadence, timing" if uploaded else "Full session design: duration, structure, exact HR targets, cadence, intervals if any"}]

— KEY CUES —
[3 specific things to focus on — numbers, not vague advice]

— RED FLAGS —
[exact conditions to stop or pull back — be specific about HR numbers, pain signals]"""

    brief = _ask_claude(_coach_system(), prompt, max_tokens=2048)

    # Persist to conversation history
    session_label = req.type.replace("-", " ").title()
    title = f"{session_label} — {today}"
    conv_id = _create_conversation("coach", title)
    _add_message(conv_id, "user", f"Design a {req.type} training session for {today}")
    _add_message(conv_id, "assistant", brief)

    return {
        "date": today,
        "type": req.type,
        "brief": brief,
        "uploaded_workouts": uploaded,
        "conversation_id": conv_id,
        "title": title,
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
    conversation_id: int | None = None
    kind: str = "ask"  # 'coach' | 'analyze' | 'ask'


@app.post("/chat", dependencies=[AUTH])
def chat(req: ChatRequest):
    """Multi-turn coaching chat. Pass conversation_id to continue an existing thread."""
    kind = req.kind if req.kind in ("coach", "analyze", "ask") else "ask"

    # Live metrics only for 'ask' kind (avoid extra API calls for follow-ups on coach/analyze)
    live_context = _live_context_for_chat() if kind == "ask" else ""

    # Get or create conversation
    conv_id = req.conversation_id
    title: str
    if conv_id is not None:
        existing = _get_conversation_detail(conv_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Conversation not found")
        title = existing.get("title") or req.message[:80]
    else:
        title = req.message[:80]
        conv_id = _create_conversation(kind, title)

    # Persist user message
    _add_message(conv_id, "user", req.message)

    # Build full message history for Claude (all prior turns + new user message)
    all_messages = _get_messages(conv_id)
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Call Claude with full conversation context
    resp = _claude.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        system=_system_for_kind(kind, live_context),
        messages=claude_messages,
    )
    reply_text = resp.content[0].text

    # Persist assistant reply and update conversation timestamp
    assistant_msg = _add_message(conv_id, "assistant", reply_text)
    _touch_conversation(conv_id)

    return {
        "conversation_id": conv_id,
        "title": title,
        "message": assistant_msg,
    }


# ── GET /conversations ────────────────────────────────────────────────────────

@app.get("/conversations", dependencies=[AUTH])
def list_conversations(kind: str | None = None):
    """List conversations, optionally filtered by kind (coach | analyze | ask)."""
    return {"conversations": _list_conversations(kind)}


# ── GET /conversations/{id} ───────────────────────────────────────────────────

@app.get("/conversations/{conv_id}", dependencies=[AUTH])
def get_conversation(conv_id: int):
    """Get a full conversation with all its messages."""
    conv = _get_conversation_detail(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


# ── DELETE /conversations/{id} ────────────────────────────────────────────────

@app.delete("/conversations/{conv_id}", dependencies=[AUTH])
def delete_conversation(conv_id: int):
    """Delete a conversation and all its messages."""
    if not _delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": conv_id}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("COACH_HOST", "127.0.0.1")
    uvicorn.run("server:app", host=host, port=PORT, reload=False)
