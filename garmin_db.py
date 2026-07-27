#!/usr/bin/env python3
"""
Garmin Connect local SQLite database.

Syncs your full Garmin history for fast offline access and coaching analysis.
The /coach command queries this DB for historical trends instead of hitting
the Garmin API every time.

Usage:
    uv run python garmin_db.py sync                     # Incremental (since last sync)
    uv run python garmin_db.py sync --full              # Full backfill from 2025-04-01
    uv run python garmin_db.py sync --since 2026-01-01  # From a specific date
    uv run python garmin_db.py stats                    # DB summary
    uv run python garmin_db.py query "SELECT ..."       # Raw SQL
    uv run python garmin_db.py analyze --period week --format table
    uv run python garmin_db.py analyze --since 2026-05-25 --until 2026-07-06 --format json
    uv run python garmin_db.py evaluate --format json        # most recent run + load metrics
    uv run python garmin_db.py evaluate --activity 23572487748 --format json
"""

import argparse
import contextlib
import json
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from garminconnect import Garmin
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# ─── Config ──────────────────────────────────────────────────────────────────

TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"
DB_PATH = Path.home() / ".config" / "garmin-connect-cli" / "garmin.db"
SYNC_START = date(2024, 5, 1)  # Garmin API retention limit (~2 years)
API_DELAY = 0.3  # Seconds between per-day API calls
RUN_TYPES = frozenset({"running", "treadmill_running", "track_running"})
# Activity types that contribute to systemic training load (CTL/ATL/TSB): runs plus
# strength and generic gym/fitness-equipment sessions. ACWR stays run-only (see
# compute_load_metrics) since it gates running-injury risk specifically.
LOAD_TYPES = RUN_TYPES | frozenset({"strength_training", "fitness_equipment"})

# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id      INTEGER PRIMARY KEY,
    start_time_gmt   TEXT,
    start_time_local TEXT,
    activity_name    TEXT,
    activity_type    TEXT,
    distance_m       REAL,
    duration_s       REAL,
    moving_time_s    REAL,
    avg_hr           INTEGER,
    max_hr           INTEGER,
    avg_cadence      REAL,
    max_cadence      REAL,
    avg_speed_ms     REAL,
    calories         INTEGER,
    aerobic_te       REAL,
    anaerobic_te     REAL,
    training_load    REAL,
    avg_gct_ms       REAL,
    avg_stride_m     REAL,
    avg_vert_osc_mm  REAL,
    hr_z1_s          REAL,
    hr_z2_s          REAL,
    hr_z3_s          REAL,
    hr_z4_s          REAL,
    hr_z5_s          REAL,
    raw_json         TEXT,
    synced_at        TEXT,
    -- NOTE: kept LAST to match _migrate()'s ALTER-appended position. The
    -- activities INSERT is positional (VALUES (?,...)), so a migrated column
    -- (appended at the end) and a fresh CREATE column must sit in the same slot.
    avg_gct_balance_left REAL
);

CREATE TABLE IF NOT EXISTS health_daily (
    date                TEXT PRIMARY KEY,
    hrv_last_night_avg  INTEGER,
    hrv_weekly_avg      INTEGER,
    hrv_status          TEXT,
    hrv_baseline_low    INTEGER,
    hrv_baseline_high   INTEGER,
    sleep_score         INTEGER,
    sleep_duration_s    INTEGER,
    sleep_deep_s        INTEGER,
    sleep_rem_s         INTEGER,
    sleep_light_s       INTEGER,
    sleep_awake_s       INTEGER,
    rhr                 INTEGER,
    body_battery_high   INTEGER,
    body_battery_low    INTEGER,
    stress              INTEGER,
    synced_at           TEXT
);

CREATE TABLE IF NOT EXISTS training_daily (
    date              TEXT PRIMARY KEY,
    readiness_score   INTEGER,
    readiness_level   TEXT,
    readiness_feedback TEXT,
    acute_load        REAL,
    hrv_weekly_avg    INTEGER,
    training_status   TEXT,
    synced_at         TEXT
);

CREATE TABLE IF NOT EXISTS weight (
    date       TEXT PRIMARY KEY,
    weight_kg  REAL,
    bmi        REAL,
    synced_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_activities_type_time
    ON activities (activity_type, start_time_local);
CREATE INDEX IF NOT EXISTS idx_health_date
    ON health_daily (date);
CREATE INDEX IF NOT EXISTS idx_training_date
    ON training_daily (date);

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

CREATE TABLE IF NOT EXISTS context_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'user',
    content    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_plan (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    plan_json  TEXT NOT NULL
);
"""

# ─── DB helpers ──────────────────────────────────────────────────────────────


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after initial schema deployment."""
    migrations = [
        "ALTER TABLE health_daily   ADD COLUMN stress           INTEGER",
        "ALTER TABLE training_daily ADD COLUMN training_status  TEXT",
        "ALTER TABLE activities     ADD COLUMN avg_gct_balance_left REAL",
    ]
    for sql in migrations:
        with contextlib.suppress(Exception):  # column already exists
            conn.execute(sql)
    conn.commit()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def last_synced(conn: sqlite3.Connection, table: str, col: str = "date") -> date:
    """Return the most recent date in a table, or SYNC_START if empty."""
    row = conn.execute(f"SELECT MAX({col}) FROM {table}").fetchone()
    val = row[0] if row else None
    if not val:
        return SYNC_START
    # activities uses start_time_local (datetime string), others use date string
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return SYNC_START


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Garmin client ───────────────────────────────────────────────────────────


def get_client() -> Garmin:
    client = Garmin()
    client.login(str(TOKEN_DIR))
    return client


# ─── Sync: Activities ────────────────────────────────────────────────────────


def _parse_activity(a: dict) -> tuple:
    return (
        a.get("activityId"),
        a.get("startTimeGMT"),
        a.get("startTimeLocal"),
        a.get("activityName"),
        a.get("activityType", {}).get("typeKey"),
        a.get("distance"),
        a.get("duration"),
        a.get("movingDuration"),
        a.get("averageHR"),
        a.get("maxHR"),
        a.get("averageRunningCadenceInStepsPerMinute"),
        a.get("maxRunningCadenceInStepsPerMinute"),
        a.get("averageSpeed"),
        a.get("calories"),
        a.get("aerobicTrainingEffect"),
        a.get("anaerobicTrainingEffect"),
        a.get("activityTrainingLoad"),
        a.get("avgGroundContactTime"),
        a.get("avgStrideLength"),
        a.get("avgVerticalOscillation"),
        a.get("hrTimeInZone_1"),
        a.get("hrTimeInZone_2"),
        a.get("hrTimeInZone_3"),
        a.get("hrTimeInZone_4"),
        a.get("hrTimeInZone_5"),
        json.dumps(a),
        now_iso(),
        # avg_gct_balance_left — left-foot % of ground contact (HRM 600+ chest
        # strap only; None on wrist-measured runs). Kept last to match schema.
        a.get("avgGroundContactBalance"),
    )


def sync_activities(client: Garmin, conn: sqlite3.Connection, since: date) -> int:
    end = date.today()
    console.print(f"  Fetching activities {since} to {end}...")

    all_activities = client.get_activities_by_date(
        startdate=since.isoformat(),
        enddate=end.isoformat(),
    )

    if not all_activities:
        return 0

    conn.executemany(
        """INSERT OR REPLACE INTO activities VALUES
           (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [_parse_activity(a) for a in all_activities],
    )
    conn.commit()
    return len(all_activities)


# ─── Sync: Health (per day) ───────────────────────────────────────────────────


def _fetch_health_day(client: Garmin, d: date) -> dict:
    ds = d.isoformat()
    row = {"date": ds}

    # HRV
    try:
        hrv = client.get_hrv_data(ds)
        s = hrv.get("hrvSummary", {})
        row["hrv_last_night_avg"] = s.get("lastNightAvg")
        row["hrv_weekly_avg"] = s.get("weeklyAvg")
        row["hrv_status"] = s.get("status")
        baseline = s.get("baseline") or {}
        row["hrv_baseline_low"] = baseline.get("balancedLow")
        row["hrv_baseline_high"] = baseline.get("balancedUpper")
    except Exception as exc:
        console.print(f"  [yellow]hrv {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    # Sleep
    try:
        sleep_resp = client.get_sleep_data(ds)
        sl = sleep_resp.get("dailySleepDTO") or {}
        scores = sl.get("sleepScores") or {}
        row["sleep_score"] = scores.get("totalScore") or (scores.get("overall") or {}).get("value")
        row["sleep_duration_s"] = sl.get("sleepTimeSeconds")
        row["sleep_deep_s"] = sl.get("deepSleepSeconds")
        row["sleep_rem_s"] = sl.get("remSleepSeconds")
        row["sleep_light_s"] = sl.get("lightSleepSeconds")
        row["sleep_awake_s"] = sl.get("awakeSleepSeconds")
        if row.get("sleep_score") is None:
            console.print(f"  [yellow]sleep {ds}: score=None (sleepScores={scores})[/yellow]")
    except Exception as exc:
        console.print(f"  [yellow]sleep {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    # RHR
    try:
        rhr_resp = client.get_rhr_day(ds)
        metrics = (rhr_resp.get("allMetrics") or {}).get("metricsMap") or {}
        rhr_list = metrics.get("WELLNESS_RESTING_HEART_RATE") or []
        if rhr_list:
            row["rhr"] = int(rhr_list[0].get("value", 0)) or None
    except Exception as exc:
        console.print(f"  [yellow]rhr {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    # Body battery
    try:
        bb_resp = client.get_body_battery(ds)
        if bb_resp and isinstance(bb_resp, list):
            bb = bb_resp[0]
            vals = [v[1] for v in (bb.get("bodyBatteryValuesArray") or []) if v[1] is not None]
            row["body_battery_high"] = max(vals) if vals else None
            row["body_battery_low"] = min(vals) if vals else None
    except Exception as exc:
        console.print(f"  [yellow]body_battery {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    # Stress
    try:
        row["stress"] = (client.get_stress_data(ds) or {}).get("overallStressLevel")
    except Exception as exc:
        console.print(f"  [yellow]stress {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    row["synced_at"] = now_iso()
    return row


_HEALTH_COLS = [
    "date",
    "hrv_last_night_avg",
    "hrv_weekly_avg",
    "hrv_status",
    "hrv_baseline_low",
    "hrv_baseline_high",
    "sleep_score",
    "sleep_duration_s",
    "sleep_deep_s",
    "sleep_rem_s",
    "sleep_light_s",
    "sleep_awake_s",
    "rhr",
    "body_battery_high",
    "body_battery_low",
    "stress",
    "synced_at",
]


def sync_health(client: Garmin, conn: sqlite3.Connection, since: date) -> int:
    days = list(date_range(since, date.today()))
    count = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("  Health metrics", total=len(days))
        for d in days:
            row = _fetch_health_day(client, d)
            conn.execute(
                """INSERT OR REPLACE INTO health_daily
                   (date, hrv_last_night_avg, hrv_weekly_avg, hrv_status,
                    hrv_baseline_low, hrv_baseline_high, sleep_score,
                    sleep_duration_s, sleep_deep_s, sleep_rem_s,
                    sleep_light_s, sleep_awake_s, rhr,
                    body_battery_high, body_battery_low, stress, synced_at)
                   VALUES
                   (:date, :hrv_last_night_avg, :hrv_weekly_avg, :hrv_status,
                    :hrv_baseline_low, :hrv_baseline_high, :sleep_score,
                    :sleep_duration_s, :sleep_deep_s, :sleep_rem_s,
                    :sleep_light_s, :sleep_awake_s, :rhr,
                    :body_battery_high, :body_battery_low, :stress, :synced_at)""",
                {k: row.get(k) for k in _HEALTH_COLS},
            )
            count += 1
            progress.advance(task)
    conn.commit()
    return count


# ─── Sync: Training readiness (per day) ──────────────────────────────────────


def _fetch_training_day(client: Garmin, d: date) -> dict:
    ds = d.isoformat()
    row = {"date": ds, "synced_at": now_iso()}
    try:
        resp = client.get_training_readiness(ds)
        if resp:
            # List is newest-first; resp[0] is the most recent calculation for the day
            # (post-exercise reset if a workout occurred, otherwise morning wake-up reading).
            r = resp[0] if isinstance(resp, list) else resp
            row["readiness_score"] = r.get("readinessScore") or r.get("score")
            row["readiness_level"] = r.get("readinessLevel") or r.get("level")
            row["readiness_feedback"] = r.get("feedbackShort") or r.get("readinessFeedbackPhrase")
            row["acute_load"] = r.get("acuteLoad")
            row["hrv_weekly_avg"] = r.get("hrvWeeklyAverage")
            if row.get("readiness_score") is None:
                console.print(
                    f"  [yellow]readiness {ds}: score=None (raw keys={list(r.keys())})[/yellow]"
                )
        else:
            console.print(
                f"  [yellow]readiness {ds}: empty response "
                f"(type={type(resp).__name__}, val={resp!r:.100})[/yellow]"
            )
    except Exception as exc:
        console.print(f"  [yellow]readiness {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    # Training status
    try:
        row["training_status"] = (client.get_training_status(ds) or {}).get("trainingStatusPhrase")
    except Exception as exc:
        console.print(f"  [yellow]training_status {ds}: {type(exc).__name__}: {exc}[/yellow]")
    time.sleep(API_DELAY)

    return row


_TRAINING_COLS = [
    "date",
    "readiness_score",
    "readiness_level",
    "readiness_feedback",
    "acute_load",
    "hrv_weekly_avg",
    "training_status",
    "synced_at",
]


def sync_training(client: Garmin, conn: sqlite3.Connection, since: date) -> int:
    days = list(date_range(since, date.today()))
    count = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("  Training readiness", total=len(days))
        for d in days:
            row = _fetch_training_day(client, d)
            conn.execute(
                """INSERT OR REPLACE INTO training_daily
                   (date, readiness_score, readiness_level, readiness_feedback,
                    acute_load, hrv_weekly_avg, training_status, synced_at)
                   VALUES
                   (:date, :readiness_score, :readiness_level, :readiness_feedback,
                    :acute_load, :hrv_weekly_avg, :training_status, :synced_at)""",
                {k: row.get(k) for k in _TRAINING_COLS},
            )
            count += 1
            progress.advance(task)
    conn.commit()
    return count


# ─── Sync: Weight ─────────────────────────────────────────────────────────────


def sync_weight(client: Garmin, conn: sqlite3.Connection, since: date) -> int:
    try:
        entries = client.get_weigh_ins(since.isoformat(), date.today().isoformat())
    except Exception as e:
        console.print(f"  [yellow]Weight sync skipped: {e}[/yellow]")
        return 0

    daily = entries.get("dateWeightList") or []
    count = 0
    for entry in daily:
        d = (entry.get("calendarDate") or entry.get("date") or "")[:10]
        if not d:
            continue
        weight_g = entry.get("weight")
        weight_kg = weight_g / 1000 if weight_g else None
        bmi = entry.get("bmi")
        conn.execute(
            "INSERT OR REPLACE INTO weight (date, weight_kg, bmi, synced_at) VALUES (?,?,?,?)",
            (d, weight_kg, bmi, now_iso()),
        )
        count += 1
    conn.commit()
    return count


# ─── Main sync ────────────────────────────────────────────────────────────────


def cmd_sync(args):
    console.print("[bold]Connecting to Garmin Connect...[/bold]")
    client = get_client()
    conn = connect()

    if args.full:
        since = SYNC_START
    elif args.since:
        since = date.fromisoformat(args.since)
    else:
        # Incremental: find the oldest last-sync date across all tables
        since_health = last_synced(conn, "health_daily", "date")
        since_training = last_synced(conn, "training_daily", "date")
        since_activities = last_synced(conn, "activities", "start_time_local")
        since = min(since_health, since_training, since_activities)
        # Back up 2 days to catch late-arriving data
        since = max(SYNC_START, since - timedelta(days=2))

    console.print(f"[bold]Syncing from[/bold] {since} [bold]to[/bold] {date.today()}")

    console.print("[bold cyan]Activities[/bold cyan]")
    n = sync_activities(client, conn, since)
    console.print(f"  [green]{n} activities synced[/green]\n")

    console.print("[bold cyan]Health metrics (HRV / sleep / RHR / body battery)[/bold cyan]")
    n = sync_health(client, conn, since)
    console.print(f"  [green]{n} days synced[/green]\n")

    console.print("[bold cyan]Training readiness[/bold cyan]")
    n = sync_training(client, conn, since)
    console.print(f"  [green]{n} days synced[/green]\n")

    console.print("[bold cyan]Weight[/bold cyan]")
    n = sync_weight(client, conn, since)
    console.print(f"  [green]{n} entries synced[/green]\n")

    console.print("[bold green]Sync complete.[/bold green]")
    console.print(f"DB: {DB_PATH}")


# ─── Stats ────────────────────────────────────────────────────────────────────


def cmd_stats(args):
    conn = connect()

    table = Table(title="Garmin DB Summary", show_lines=True)
    table.add_column("Table", style="bold")
    table.add_column("Rows", justify="right")
    table.add_column("Date range")

    for tbl, date_col in [
        ("activities", "start_time_local"),
        ("health_daily", "date"),
        ("training_daily", "date"),
        ("weight", "date"),
        ("context_entries", "created_at"),
    ]:
        row = conn.execute(
            f"SELECT COUNT(*), MIN({date_col}), MAX({date_col}) FROM {tbl}"
        ).fetchone()
        count, min_d, max_d = row
        date_range_str = f"{(min_d or '')[:10]} to {(max_d or '')[:10]}" if count else "-"
        table.add_row(tbl, str(count), date_range_str)

    console.print(table)

    # Quick coaching insights
    console.print()
    console.print("[bold]Last 7 days - Running volume[/bold]")
    _run_ph = ",".join("?" * len(RUN_TYPES))
    rows = conn.execute(
        f"""SELECT date(start_time_local) as day,
               round(sum(distance_m)/1000, 1) as km,
               round(avg(avg_cadence), 0) as cadence,
               round(avg(avg_hr), 0) as avg_hr
        FROM activities
        WHERE activity_type IN ({_run_ph})
          AND date(start_time_local) >= date('now', '-7 days')
        GROUP BY day ORDER BY day DESC""",
        tuple(RUN_TYPES),
    ).fetchall()
    if rows:
        t2 = Table(show_header=True)
        t2.add_column("Date")
        t2.add_column("km", justify="right")
        t2.add_column("Cadence", justify="right")
        t2.add_column("Avg HR", justify="right")
        for r in rows:
            t2.add_row(r["day"], str(r["km"]), str(r["cadence"]), str(r["avg_hr"]))
        console.print(t2)
    else:
        console.print("  No running activities in the last 7 days.")

    console.print()
    console.print("[bold]Last 7 days - HRV & Readiness[/bold]")
    rows = conn.execute("""
        SELECT h.date,
               h.hrv_last_night_avg as hrv,
               h.hrv_status,
               t.readiness_score as readiness,
               t.readiness_level
        FROM health_daily h
        LEFT JOIN training_daily t ON t.date = h.date
        WHERE h.date >= date('now', '-7 days')
        ORDER BY h.date DESC
    """).fetchall()
    if rows:
        t3 = Table(show_header=True)
        t3.add_column("Date")
        t3.add_column("HRV", justify="right")
        t3.add_column("HRV Status")
        t3.add_column("Readiness", justify="right")
        t3.add_column("Level")
        for r in rows:
            t3.add_row(
                r["date"],
                str(r["hrv"] or "-"),
                r["hrv_status"] or "-",
                str(r["readiness"] or "-"),
                r["readiness_level"] or "-",
            )
        console.print(t3)

    console.print(f"\nDB: {DB_PATH}")


# ─── Raw query ────────────────────────────────────────────────────────────────


def cmd_query(args):
    conn = connect()
    try:
        rows = conn.execute(args.sql).fetchall()
    except sqlite3.Error as e:
        console.print(f"[red]SQL error: {e}[/red]")
        sys.exit(1)

    if not rows:
        console.print("No results.")
        return

    t = Table(show_lines=False)
    for col in rows[0].keys():  # noqa: SIM118 - rows[0] is sqlite3.Row, not a dict: iterating
        # it directly yields values, not column names - .keys() is required here
        t.add_column(col)
    for row in rows:
        t.add_row(*[str(v) if v is not None else "—" for v in row])
    console.print(t)


# ─── Period analysis ──────────────────────────────────────────────────────────
# Code-ified version of .claude/commands/analyze.md's Step 2 (SQL + derived
# metrics). This replaces hand-writing a throwaway analysis script every
# /analyze invocation - the derived-metric math lives here once.

ALL_METRICS = {"sleep", "hrv", "readiness", "running", "strength", "body_battery", "correlations"}


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _sleep_metrics(health_rows: list[dict]) -> dict:
    scores = [r["sleep_score"] for r in health_rows if r["sleep_score"] is not None]
    totals = [r["sleep_duration_s"] for r in health_rows if r["sleep_duration_s"]]
    deep = [r["sleep_deep_s"] for r in health_rows if r["sleep_deep_s"] is not None]
    rem = [r["sleep_rem_s"] for r in health_rows if r["sleep_rem_s"] is not None]
    awake = [r["sleep_awake_s"] for r in health_rows if r["sleep_awake_s"] is not None]
    avg_total_h = _avg(totals) / 3600 if totals else None
    avg_deep_h = _avg(deep) / 3600 if deep else None
    avg_rem_h = _avg(rem) / 3600 if rem else None
    return {
        "avg_sleep_score": _avg(scores),
        "avg_total_h": avg_total_h,
        "avg_deep_h": avg_deep_h,
        "avg_rem_h": avg_rem_h,
        "avg_awake_min": _avg(awake) / 60 if awake else None,
        "deep_pct": (avg_deep_h / avg_total_h * 100)
        if avg_total_h and avg_deep_h is not None
        else None,
        "rem_pct": (avg_rem_h / avg_total_h * 100)
        if avg_total_h and avg_rem_h is not None
        else None,
        "nights_below_7h": sum(1 for t in totals if t < 7 * 3600),
        "nights_score_under_70": sum(1 for s in scores if s < 70),
        "n_nights": len(health_rows),
    }


def _hrv_metrics(health_rows: list[dict]) -> dict:
    vals = [r["hrv_last_night_avg"] for r in health_rows if r["hrv_last_night_avg"] is not None]
    statuses = [r["hrv_status"] for r in health_rows if r["hrv_status"]]
    half = len(vals) // 2
    stress_days = [
        r["date"]
        for r in health_rows
        if r["hrv_last_night_avg"] is not None
        and r["hrv_baseline_low"] is not None
        and r["hrv_last_night_avg"] < r["hrv_baseline_low"] - 5
    ]
    return {
        "avg_hrv": _avg(vals),
        "min_hrv": min(vals) if vals else None,
        "max_hrv": max(vals) if vals else None,
        "hrv_std": statistics.pstdev(vals) if len(vals) > 1 else None,
        "status_counts": dict(Counter(statuses)),
        "first_half_avg": _avg(vals[:half]) if half else None,
        "second_half_avg": _avg(vals[half:]) if half else None,
        "stress_flag_days": stress_days,
    }


def _readiness_metrics(training_rows: list[dict]) -> dict:
    scores = [r["readiness_score"] for r in training_rows if r["readiness_score"] is not None]
    levels = [r["readiness_level"] for r in training_rows if r["readiness_level"]]
    acute = [r["acute_load"] for r in training_rows if r["acute_load"] is not None]
    return {
        "avg_readiness": _avg(scores),
        "min_readiness": min(scores) if scores else None,
        "max_readiness": max(scores) if scores else None,
        "level_counts": dict(Counter(levels)),
        "avg_acute_load": _avg(acute),
    }


def _running_metrics(activity_rows: list[dict]) -> dict:
    runs = [a for a in activity_rows if a["activity_type"] in RUN_TYPES]
    total_km = sum((a["distance_m"] or 0) for a in runs) / 1000

    zones = {z: sum((a[f"hr_z{z}_s"] or 0) for a in runs) for z in range(1, 6)}
    ztotal = sum(zones.values())
    zone_pct = {f"z{z}_pct": (zones[z] / ztotal * 100 if ztotal else None) for z in range(1, 6)}

    cadences = [a["avg_cadence"] for a in runs if a["avg_cadence"]]
    buckets = {
        "<150": 0,
        "150-154": 0,
        "155-159": 0,
        "160-164": 0,
        "165-169": 0,
        "170-174": 0,
        "175+": 0,
    }
    for c in cadences:
        if c < 150:
            buckets["<150"] += 1
        elif c < 155:
            buckets["150-154"] += 1
        elif c < 160:
            buckets["155-159"] += 1
        elif c < 165:
            buckets["160-164"] += 1
        elif c < 170:
            buckets["165-169"] += 1
        elif c < 175:
            buckets["170-174"] += 1
        else:
            buckets["175+"] += 1

    paces = [
        (a["duration_s"] / 60) / (a["distance_m"] / 1000)
        for a in runs
        if a["distance_m"] and a["duration_s"]
    ]

    longest = max(runs, key=lambda a: a["distance_m"] or 0, default=None)
    hardest = max(runs, key=lambda a: a["training_load"] or 0, default=None)

    # GCT L/R balance — chest-strap only (HRM 600+); None on wrist-measured runs.
    # avg_gct_balance_left is the left-foot %; runs without it are excluded.
    balances = [a["avg_gct_balance_left"] for a in runs if a.get("avg_gct_balance_left")]

    return {
        "total_km": round(total_km, 2),
        "total_runs": len(runs),
        "avg_hr": _avg([a["avg_hr"] for a in runs]),
        "avg_cadence": _avg(cadences),
        "avg_gct_balance_left": _avg(balances),
        "n_runs_with_balance": len(balances),
        "avg_pace_min_per_km": _avg(paces),
        "avg_aerobic_te": _avg([a["aerobic_te"] for a in runs]),
        "avg_training_load": _avg([a["training_load"] for a in runs]),
        "hr_zone_pct": zone_pct,
        "cadence_distribution": buckets,
        "longest_run_km": round((longest["distance_m"] or 0) / 1000, 2) if longest else None,
        "longest_run_date": longest["start_time_local"] if longest else None,
        "hardest_load_session": hardest["training_load"] if hardest else None,
        "hardest_load_date": hardest["start_time_local"] if hardest else None,
    }


def _strength_metrics(activity_rows: list[dict]) -> dict:
    strength = [a for a in activity_rows if a["activity_type"] == "strength_training"]
    return {
        "total_strength_sessions": len(strength),
        "avg_load": _avg([a["training_load"] for a in strength]),
        "total_load": sum((a["training_load"] or 0) for a in strength),
    }


def _body_battery_metrics(health_rows: list[dict]) -> dict:
    high = [r["body_battery_high"] for r in health_rows if r["body_battery_high"] is not None]
    low = [r["body_battery_low"] for r in health_rows if r["body_battery_low"] is not None]
    return {
        "avg_daily_high": _avg(high),
        "avg_daily_low": _avg(low),
        "days_high_below_60": sum(1 for b in high if b < 60),
    }


def _iso_week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso[0], iso[1])


def _weekly_subtotals(
    health_rows: list[dict], training_rows: list[dict], activity_rows: list[dict]
) -> list[dict]:
    runs = [a for a in activity_rows if a["activity_type"] in RUN_TYPES]
    by_week: dict[tuple[int, int], dict] = {}

    def bucket(key):
        return by_week.setdefault(key, {"run_km": 0.0, "hrv": [], "sleep": [], "readiness": []})

    for a in runs:
        d = datetime.strptime(a["start_time_local"][:10], "%Y-%m-%d").date()
        bucket(_iso_week_key(d))["run_km"] += (a["distance_m"] or 0) / 1000

    for r in health_rows:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        b = bucket(_iso_week_key(d))
        if r["hrv_last_night_avg"] is not None:
            b["hrv"].append(r["hrv_last_night_avg"])
        if r["sleep_score"] is not None:
            b["sleep"].append(r["sleep_score"])

    for r in training_rows:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        b = bucket(_iso_week_key(d))
        if r["readiness_score"] is not None:
            b["readiness"].append(r["readiness_score"])

    result = []
    for iso_year, iso_week in sorted(by_week):
        v = by_week[(iso_year, iso_week)]
        result.append(
            {
                "iso_year": iso_year,
                "iso_week": iso_week,
                "run_km": round(v["run_km"], 2),
                "avg_hrv": _avg(v["hrv"]),
                "avg_sleep_score": _avg(v["sleep"]),
                "avg_readiness": _avg(v["readiness"]),
            }
        )
    return result


def _corr(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 7:
        return None
    xs, ys = zip(*pairs, strict=True)
    try:
        return statistics.correlation(xs, ys)
    except (statistics.StatisticsError, ZeroDivisionError):
        return None


def _correlations(health_rows: list[dict], training_rows: list[dict]) -> dict:
    h_by_date = {r["date"]: r for r in health_rows}
    t_by_date = {r["date"]: r for r in training_rows}

    hrv_next_readiness = []
    for d in sorted(h_by_date):
        hrv = h_by_date[d]["hrv_last_night_avg"]
        if hrv is None:
            continue
        nxt = (datetime.strptime(d, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        if nxt in t_by_date and t_by_date[nxt]["readiness_score"] is not None:
            hrv_next_readiness.append((hrv, t_by_date[nxt]["readiness_score"]))

    sleep_hrv = [
        (h_by_date[d]["sleep_score"], h_by_date[d]["hrv_last_night_avg"])
        for d in h_by_date
        if h_by_date[d]["sleep_score"] is not None
        and h_by_date[d]["hrv_last_night_avg"] is not None
    ]
    deep_hrv = [
        (h_by_date[d]["sleep_deep_s"], h_by_date[d]["hrv_last_night_avg"])
        for d in h_by_date
        if h_by_date[d]["sleep_deep_s"] is not None
        and h_by_date[d]["hrv_last_night_avg"] is not None
    ]
    bb_readiness = []
    for d in sorted(h_by_date):
        bb = h_by_date[d]["body_battery_high"]
        if bb is not None and d in t_by_date and t_by_date[d]["readiness_score"] is not None:
            bb_readiness.append((bb, t_by_date[d]["readiness_score"]))

    return {
        "hrv_vs_next_day_readiness": {"n": len(hrv_next_readiness), "r": _corr(hrv_next_readiness)},
        "sleep_score_vs_same_night_hrv": {"n": len(sleep_hrv), "r": _corr(sleep_hrv)},
        "deep_sleep_vs_hrv": {"n": len(deep_hrv), "r": _corr(deep_hrv)},
        "body_battery_high_vs_readiness": {"n": len(bb_readiness), "r": _corr(bb_readiness)},
    }


def flag_outlier_days(health_rows: list[dict], training_rows: list[dict]) -> list[dict]:
    """Extract specific days worth calling out by date, for callers (e.g. server.py's
    /analyze) that send Claude only aggregates, not full daily_rows, but still want
    the report to be able to cite concrete dates for red flags."""
    t_by_date = {r["date"]: r for r in training_rows}
    flagged: dict[str, dict] = {}

    for r in health_rows:
        if r["hrv_status"] == "LOW":
            flagged.setdefault(r["date"], {"date": r["date"]})["hrv_status"] = "LOW"

    for r in training_rows:
        if r["readiness_score"] is not None and r["readiness_score"] < 40:
            flagged.setdefault(r["date"], {"date": r["date"]})["readiness_score"] = r[
                "readiness_score"
            ]

    for r in health_rows:
        d = r["date"]
        readiness = t_by_date.get(d, {}).get("readiness_score")
        hrv_low = r["hrv_status"] == "LOW"
        bb_low = r["body_battery_high"] is not None and r["body_battery_high"] < 60
        if hrv_low and bb_low and readiness is not None and readiness < 40:
            flagged.setdefault(d, {"date": d})["all_systems_stress"] = True

    return sorted(flagged.values(), key=lambda x: x["date"])


def find_latest_run(conn: sqlite3.Connection, as_of: date | None = None) -> int | None:
    """activity_id of the most recent run (running/treadmill/track), optionally
    on or before as_of (inclusive). None if there are no runs."""
    placeholders = ",".join("?" for _ in RUN_TYPES)
    params: list = list(RUN_TYPES)
    clause = ""
    if as_of is not None:
        clause = " AND start_time_local <= ?"
        params.append(as_of.isoformat() + " 23:59:59")
    row = conn.execute(
        f"""SELECT activity_id FROM activities
            WHERE activity_type IN ({placeholders}){clause}
            ORDER BY start_time_local DESC LIMIT 1""",
        params,
    ).fetchone()
    return row["activity_id"] if row else None


def summarize_activity(conn: sqlite3.Connection, activity_id: int) -> dict | None:
    """Single-activity summary for post-workout evaluation: distance, pace, HR,
    cadence, HR-zone split, training effect and load. Returns None if the id
    isn't in the DB (caller should sync first)."""
    row = conn.execute(
        """SELECT activity_id, start_time_local, activity_name, activity_type,
                  distance_m, duration_s, avg_hr, max_hr, avg_cadence,
                  aerobic_te, anaerobic_te, training_load, avg_gct_balance_left,
                  hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
           FROM activities WHERE activity_id = ?""",
        (activity_id,),
    ).fetchone()
    if row is None:
        return None
    r = dict(row)
    zones = {z: (r[f"hr_z{z}_s"] or 0) for z in range(1, 6)}
    ztotal = sum(zones.values())
    zone_pct = {
        f"z{z}_pct": (round(zones[z] / ztotal * 100, 1) if ztotal else None) for z in range(1, 6)
    }
    z3plus = round(sum(zones[z] for z in (3, 4, 5)) / ztotal * 100, 1) if ztotal else None
    dist_km = (r["distance_m"] or 0) / 1000
    dur_min = (r["duration_s"] or 0) / 60

    def _rnd(v, n=1):
        return round(v, n) if v is not None else None

    return {
        "activity_id": r["activity_id"],
        "date": r["start_time_local"],
        "name": r["activity_name"],
        "type": r["activity_type"],
        "distance_km": round(dist_km, 2),
        "duration_min": round(dur_min, 1),
        "avg_hr": r["avg_hr"],
        "max_hr": r["max_hr"],
        "avg_cadence": _rnd(r["avg_cadence"]),
        "aerobic_te": _rnd(r["aerobic_te"], 2),
        "anaerobic_te": _rnd(r["anaerobic_te"], 2),
        "training_load": _rnd(r["training_load"]),
        "avg_pace_min_per_km": round(dur_min / dist_km, 2) if dist_km else None,
        "hr_zone_pct": zone_pct,
        "hr_z3plus_pct": z3plus,
        # Left-foot GCT %; None on wrist-measured runs (chest strap HRM 600+ only).
        "avg_gct_balance_left": _rnd(r["avg_gct_balance_left"]),
    }


def compute_load_metrics(
    conn: sqlite3.Connection,
    as_of: date,
    *,
    acute_days: int = 7,
    chronic_days: int = 28,
    ctl_tau: int = 42,
    atl_tau: int = 7,
    warmup_days: int = 84,
) -> dict:
    """Training-load / fitness-fatigue metrics as of `as_of` (inclusive).

    - ACWR (Gabbett): acute = run load over the last `acute_days`; chronic = mean
      weekly run load over `chronic_days`; ratio = acute / chronic. Run-only, since
      ACWR gates running-injury risk. 0.8-1.3 safe, >1.5 high risk.
    - CTL/ATL/TSB (Banister impulse-response, EWMA): daily systemic load (LOAD_TYPES)
      smoothed with time constants `ctl_tau` (fitness) and `atl_tau` (fatigue).
      TSB = CTL - ATL (form). The EWMA is warmed up over `warmup_days` before `as_of`
      so the 42-day CTL constant isn't cold-started from zero at the window edge.
    """
    # Daily systemic load series over the warmup window, one bucket per calendar day.
    warm_start = as_of - timedelta(days=warmup_days)
    load_placeholders = ",".join("?" for _ in LOAD_TYPES)
    daily_load: dict[str, float] = {}
    for r in conn.execute(
        f"""SELECT substr(start_time_local, 1, 10) AS d, SUM(training_load) AS load
            FROM activities
            WHERE start_time_local BETWEEN ? AND ?
              AND activity_type IN ({load_placeholders})
            GROUP BY d""",
        [warm_start.isoformat(), as_of.isoformat() + " 23:59:59", *LOAD_TYPES],
    ).fetchall():
        daily_load[r["d"]] = r["load"] or 0.0

    # Walk every calendar day (including rest days, so decay applies correctly).
    ctl = atl = 0.0
    k_ctl = 1 - 1 / ctl_tau
    k_atl = 1 - 1 / atl_tau
    for d in date_range(warm_start, as_of):
        load = daily_load.get(d.isoformat(), 0.0)
        ctl = ctl * k_ctl + load * (1 - k_ctl)
        atl = atl * k_atl + load * (1 - k_atl)

    # ACWR: run-only load over acute vs chronic windows (both ending at as_of).
    run_placeholders = ",".join("?" for _ in RUN_TYPES)

    def _run_load(days: int) -> float:
        start = as_of - timedelta(days=days - 1)
        row = conn.execute(
            f"""SELECT SUM(training_load) FROM activities
                WHERE start_time_local BETWEEN ? AND ?
                  AND activity_type IN ({run_placeholders})""",
            [start.isoformat(), as_of.isoformat() + " 23:59:59", *RUN_TYPES],
        ).fetchone()
        return row[0] or 0.0

    acute = _run_load(acute_days)
    chronic_total = _run_load(chronic_days)
    chronic_weekly = chronic_total / (chronic_days / 7)
    acwr = round(acute / chronic_weekly, 2) if chronic_weekly else None

    return {
        "as_of": as_of.isoformat(),
        "acute_load": round(acute, 1),
        "chronic_load_weekly_avg": round(chronic_weekly, 1),
        "acwr": acwr,
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(ctl - atl, 1),
    }


def compute_period_analysis(
    conn: sqlite3.Connection, start: date, end: date, metrics: set[str] | None = None
) -> dict:
    """Compute derived analysis metrics for [start, end] (inclusive).

    Returns aggregates for each requested metric group plus raw per-day rows
    under "daily_rows" (health/training/activities) - the interpretation step
    needs to cite specific dates (e.g. "flag days with all-systems-stress"),
    and the query already fetched the rows, so they're always included.
    """
    if metrics is None:
        metrics = set(ALL_METRICS)
    unknown = metrics - ALL_METRICS
    if unknown:
        raise ValueError(f"Unknown metrics: {sorted(unknown)} (valid: {sorted(ALL_METRICS)})")

    start_s, end_s = start.isoformat(), end.isoformat()

    # Explicit column lists - never SELECT * here: activities.raw_json is the entire raw
    # Garmin API payload per activity (~1,500 tokens each) and nothing downstream reads it
    # or synced_at; dumping them into every result silently bloats any consumer (Claude
    # Code's /analyze --format json, and server.py once it adopts this function) by tens
    # to hundreds of thousands of tokens for multi-week periods.
    health_rows = [
        dict(r)
        for r in conn.execute(
            """SELECT date, hrv_last_night_avg, hrv_weekly_avg, hrv_status,
                      hrv_baseline_low, hrv_baseline_high, sleep_score, sleep_duration_s,
                      sleep_deep_s, sleep_rem_s, sleep_light_s, sleep_awake_s, rhr,
                      body_battery_high, body_battery_low, stress
               FROM health_daily WHERE date BETWEEN ? AND ? ORDER BY date""",
            (start_s, end_s),
        ).fetchall()
    ]
    training_rows = [
        dict(r)
        for r in conn.execute(
            """SELECT date, readiness_score, readiness_level, readiness_feedback,
                      acute_load, hrv_weekly_avg, training_status
               FROM training_daily WHERE date BETWEEN ? AND ? ORDER BY date""",
            (start_s, end_s),
        ).fetchall()
    ]
    activity_rows = [
        dict(r)
        for r in conn.execute(
            """SELECT activity_id, start_time_gmt, start_time_local, activity_name,
                      activity_type, distance_m, duration_s, moving_time_s, avg_hr, max_hr,
                      avg_cadence, max_cadence, avg_speed_ms, calories, aerobic_te,
                      anaerobic_te, training_load, avg_gct_ms, avg_stride_m,
                      avg_vert_osc_mm, avg_gct_balance_left,
                      hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
               FROM activities
               WHERE start_time_local BETWEEN ? AND ? ORDER BY start_time_local""",
            (start_s, end_s + " 23:59:59"),
        ).fetchall()
    ]

    days = (end - start).days + 1
    result: dict = {
        "period": {"start": start_s, "end": end_s, "days": days},
        "daily_rows": {
            "health": health_rows,
            "training": training_rows,
            "activities": activity_rows,
        },
    }

    if "sleep" in metrics:
        result["sleep"] = _sleep_metrics(health_rows)
    if "hrv" in metrics:
        result["hrv"] = _hrv_metrics(health_rows)
    if "readiness" in metrics:
        result["readiness"] = _readiness_metrics(training_rows)
    if "running" in metrics:
        result["running"] = _running_metrics(activity_rows)
    if "strength" in metrics:
        result["strength"] = _strength_metrics(activity_rows)
    if "body_battery" in metrics:
        result["body_battery"] = _body_battery_metrics(health_rows)

    result["weekly_subtotals"] = (
        _weekly_subtotals(health_rows, training_rows, activity_rows) if days >= 28 else None
    )

    if "correlations" in metrics:
        result["correlations"] = _correlations(health_rows, training_rows)

    return result


def _resolve_period(period: str | None, today: date) -> tuple[date, date]:
    """Mirror .claude/commands/analyze.md's Step 1 date-range table."""
    if not period:
        return today - timedelta(days=6), today
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "last-week":
        this_monday = today - timedelta(days=today.weekday())
        return this_monday - timedelta(days=7), this_monday - timedelta(days=1)
    if period == "month":
        return today.replace(day=1), today
    if period == "last-month":
        last_month_end = today.replace(day=1) - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    if period == "year":
        return today.replace(month=1, day=1), today
    if period == "last-year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if re.fullmatch(r"\d{4}", period):
        y = int(period)
        return date(y, 1, 1), date(y, 12, 31)
    if re.fullmatch(r"\d{4}-\d{2}", period):
        y, m = (int(x) for x in period.split("-"))
        start = date(y, m, 1)
        end = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
        return start, end
    if ":" in period:
        s, e = period.split(":", 1)
        try:
            return date.fromisoformat(s.strip()), date.fromisoformat(e.strip())
        except ValueError as exc:
            raise ValueError(
                f"Unrecognized --period value: {period!r} (bad date in range: {exc})"
            ) from exc
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
        try:
            d = date.fromisoformat(period)
        except ValueError as exc:
            raise ValueError(f"Unrecognized --period value: {period!r} (bad date: {exc})") from exc
        return d, d
    raise ValueError(
        f"Unrecognized --period value: {period!r} (expected week/last-week/month/last-month/"
        "year/last-year/YYYY/YYYY-MM/YYYY-MM-DD/YYYY-MM-DD:YYYY-MM-DD)"
    )


def cmd_analyze(args):
    today = date.today()

    if args.period and (args.since or args.until):
        console.print("[red]--period cannot be combined with --since/--until[/red]")
        sys.exit(1)

    try:
        if args.since or args.until:
            start = date.fromisoformat(args.since) if args.since else today - timedelta(days=6)
            end = date.fromisoformat(args.until) if args.until else today
        else:
            start, end = _resolve_period(args.period, today)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    metrics = (
        None if args.metrics in (None, "all") else {m.strip() for m in args.metrics.split(",")}
    )

    conn = connect()
    try:
        result = compute_period_analysis(conn, start, end, metrics)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
        return

    console.print(
        f"[bold]Period: {result['period']['start']} to {result['period']['end']} "
        f"({result['period']['days']} days)[/bold]\n"
    )

    for key in ("sleep", "hrv", "readiness", "running", "strength", "body_battery"):
        if key not in result:
            continue
        t = Table(title=key.replace("_", " ").title(), show_header=True)
        t.add_column("Metric")
        t.add_column("Value")
        for k, v in result[key].items():
            t.add_row(k, str(v))
        console.print(t)
        console.print()

    if result.get("weekly_subtotals"):
        t = Table(title="Weekly Subtotals")
        t.add_column("ISO Week")
        t.add_column("Run km")
        t.add_column("Avg HRV")
        t.add_column("Avg Sleep")
        t.add_column("Avg Readiness")
        for w in result["weekly_subtotals"]:
            t.add_row(
                f"{w['iso_year']}-W{w['iso_week']:02d}",
                str(w["run_km"]),
                str(w["avg_hrv"]),
                str(w["avg_sleep_score"]),
                str(w["avg_readiness"]),
            )
        console.print(t)
        console.print()

    if result.get("correlations"):
        t = Table(title="Correlations")
        t.add_column("Pair")
        t.add_column("N")
        t.add_column("r")
        for k, v in result["correlations"].items():
            t.add_row(k, str(v["n"]), str(v["r"]))
        console.print(t)

    console.print(f"\nDB: {DB_PATH}")


def cmd_evaluate(args):
    conn = connect()

    if args.activity:
        aid = int(args.activity)
    else:
        aid = find_latest_run(conn)
        if aid is None:
            console.print("[red]No runs found in the DB — sync first.[/red]")
            sys.exit(1)

    summary = summarize_activity(conn, aid)
    if summary is None:
        console.print(
            f"[red]Activity {aid} not in DB — run 'garmin_db.py sync' to backfill it first.[/red]"
        )
        sys.exit(1)

    try:
        as_of = (
            date.fromisoformat(args.date) if args.date else date.fromisoformat(summary["date"][:10])
        )
    except ValueError as e:
        console.print(f"[red]Bad --date: {e}[/red]")
        sys.exit(1)

    load = compute_load_metrics(conn, as_of)

    # Recovery context: the few days of HRV/sleep/RHR and readiness ending at as_of.
    health = [
        dict(r)
        for r in conn.execute(
            """SELECT date, hrv_last_night_avg, hrv_weekly_avg, hrv_status,
                      hrv_baseline_low, hrv_baseline_high, sleep_score, sleep_deep_s,
                      sleep_awake_s, rhr, body_battery_high, body_battery_low
               FROM health_daily WHERE date <= ? ORDER BY date DESC LIMIT 3""",
            (as_of.isoformat(),),
        ).fetchall()
    ]
    readiness = [
        dict(r)
        for r in conn.execute(
            """SELECT date, readiness_score, readiness_level, readiness_feedback, acute_load
               FROM training_daily WHERE date <= ? ORDER BY date DESC LIMIT 4""",
            (as_of.isoformat(),),
        ).fetchall()
    ]

    result = {
        "activity": summary,
        "load_metrics": load,
        "recovery": {"health_recent": health, "readiness_recent": readiness},
    }

    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"[bold]Activity: {summary['name']} — {summary['date']}[/bold]")
    console.print(
        f"  {summary['distance_km']} km / {summary['duration_min']} min / "
        f"{summary['avg_pace_min_per_km']} min/km"
    )
    console.print(
        f"  HR avg {summary['avg_hr']} / max {summary['max_hr']} · "
        f"cadence {summary['avg_cadence']} · Z3+ {summary['hr_z3plus_pct']}% · "
        f"load {summary['training_load']}\n"
    )
    t = Table(title="Load Metrics", show_header=True)
    t.add_column("Metric")
    t.add_column("Value")
    for k, v in load.items():
        t.add_row(k, str(v))
    console.print(t)
    console.print(f"\nDB: {DB_PATH}")


# ─── CLI entry point ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Garmin Connect local SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # sync
    p_sync = sub.add_parser("sync", help="Sync data from Garmin Connect")
    p_sync.add_argument("--full", action="store_true", help=f"Full backfill from {SYNC_START}")
    p_sync.add_argument("--since", metavar="YYYY-MM-DD", help="Sync from this date")

    # stats
    sub.add_parser("stats", help="Database summary and recent coaching data")

    # query
    p_query = sub.add_parser("query", help="Run a raw SQL query")
    p_query.add_argument("sql", help="SQL statement to execute")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Compute period analysis metrics")
    p_analyze.add_argument("--since", metavar="YYYY-MM-DD", help="Explicit start date")
    p_analyze.add_argument(
        "--until", metavar="YYYY-MM-DD", help="Explicit end date (default: today)"
    )
    p_analyze.add_argument(
        "--period",
        metavar="RANGE",
        help="week|last-week|month|last-month|year|last-year|YYYY|YYYY-MM "
        "(mutually exclusive with --since/--until; default: last 7 days)",
    )
    p_analyze.add_argument(
        "--metrics",
        default="all",
        help="Comma list: sleep,hrv,readiness,running,strength,body_battery,correlations "
        "(default: all)",
    )
    p_analyze.add_argument("--format", choices=["table", "json"], default="table")

    # evaluate
    p_eval = sub.add_parser(
        "evaluate", help="Post-workout evaluation: activity summary + ACWR/CTL/ATL/TSB"
    )
    p_eval.add_argument(
        "--activity", metavar="ID", help="Activity id (default: most recent run in the DB)"
    )
    p_eval.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="As-of date for load metrics (default: the activity's own date)",
    )
    p_eval.add_argument("--format", choices=["table", "json"], default="table")

    args = parser.parse_args()

    dispatch = {
        "sync": cmd_sync,
        "stats": cmd_stats,
        "query": cmd_query,
        "analyze": cmd_analyze,
        "evaluate": cmd_evaluate,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
