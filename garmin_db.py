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
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from garminconnect import Garmin
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# ─── Config ──────────────────────────────────────────────────────────────────

TOKEN_DIR  = Path.home() / ".config" / "garmin-connect-cli" / "tokens"
DB_PATH    = Path.home() / ".config" / "garmin-connect-cli" / "garmin.db"
SYNC_START = date(2024, 5, 1)   # Garmin API retention limit (~2 years)
API_DELAY  = 0.3                # Seconds between per-day API calls

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
    synced_at        TEXT
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
    synced_at           TEXT
);

CREATE TABLE IF NOT EXISTS training_daily (
    date              TEXT PRIMARY KEY,
    readiness_score   INTEGER,
    readiness_level   TEXT,
    readiness_feedback TEXT,
    acute_load        REAL,
    hrv_weekly_avg    INTEGER,
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
"""

# ─── DB helpers ──────────────────────────────────────────────────────────────

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
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
    )


def sync_activities(client: Garmin, conn: sqlite3.Connection, since: date) -> int:
    end = date.today()
    console.print(f"  Fetching activities {since} to {end}...")

    # Garmin returns max ~200 per call; page through if needed
    all_activities = []
    start_idx = 0
    batch = 200
    while True:
        chunk = client.get_activities_by_date(
            startdate=since.isoformat(),
            enddate=end.isoformat(),
        )
        if not chunk:
            break
        # get_activities_by_date returns all in range, not paginated
        all_activities = chunk
        break

    if not all_activities:
        return 0

    conn.executemany(
        """INSERT OR REPLACE INTO activities VALUES
           (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
    except Exception:
        pass
    time.sleep(API_DELAY)

    # Sleep
    try:
        sleep_resp = client.get_sleep_data(ds)
        sl = sleep_resp.get("dailySleepDTO") or {}
        scores = sl.get("sleepScores") or {}
        row["sleep_score"] = (
            scores.get("totalScore")
            or (scores.get("overall") or {}).get("value")
        )
        row["sleep_duration_s"] = sl.get("sleepTimeSeconds")
        row["sleep_deep_s"] = sl.get("deepSleepSeconds")
        row["sleep_rem_s"] = sl.get("remSleepSeconds")
        row["sleep_light_s"] = sl.get("lightSleepSeconds")
        row["sleep_awake_s"] = sl.get("awakeSleepSeconds")
    except Exception:
        pass
    time.sleep(API_DELAY)

    # RHR
    try:
        rhr_resp = client.get_rhr_day(ds)
        metrics = (rhr_resp.get("allMetrics") or {}).get("metricsMap") or {}
        rhr_list = metrics.get("WELLNESS_RESTING_HEART_RATE") or []
        if rhr_list:
            row["rhr"] = int(rhr_list[0].get("value", 0)) or None
    except Exception:
        pass
    time.sleep(API_DELAY)

    # Body battery
    try:
        bb_resp = client.get_body_battery(ds)
        if bb_resp and isinstance(bb_resp, list):
            bb = bb_resp[0]
            vals = [v[1] for v in (bb.get("bodyBatteryValuesArray") or []) if v[1] is not None]
            row["body_battery_high"] = max(vals) if vals else None
            row["body_battery_low"] = min(vals) if vals else None
    except Exception:
        pass
    time.sleep(API_DELAY)

    row["synced_at"] = now_iso()
    return row


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
                    body_battery_high, body_battery_low, synced_at)
                   VALUES
                   (:date, :hrv_last_night_avg, :hrv_weekly_avg, :hrv_status,
                    :hrv_baseline_low, :hrv_baseline_high, :sleep_score,
                    :sleep_duration_s, :sleep_deep_s, :sleep_rem_s,
                    :sleep_light_s, :sleep_awake_s, :rhr,
                    :body_battery_high, :body_battery_low, :synced_at)""",
                {k: row.get(k) for k in [
                    "date", "hrv_last_night_avg", "hrv_weekly_avg", "hrv_status",
                    "hrv_baseline_low", "hrv_baseline_high", "sleep_score",
                    "sleep_duration_s", "sleep_deep_s", "sleep_rem_s",
                    "sleep_light_s", "sleep_awake_s", "rhr",
                    "body_battery_high", "body_battery_low", "synced_at",
                ]},
            )
            conn.commit()
            count += 1
            progress.advance(task)
    return count


# ─── Sync: Training readiness (per day) ──────────────────────────────────────

def _fetch_training_day(client: Garmin, d: date) -> dict:
    ds = d.isoformat()
    row = {"date": ds, "synced_at": now_iso()}
    try:
        resp = client.get_training_readiness(ds)
        if resp:
            # API returns a list for historical days, sometimes a dict for today
            r = resp[0] if isinstance(resp, list) else resp
            row["readiness_score"] = r.get("score") or r.get("readinessScore")
            row["readiness_level"] = r.get("level") or r.get("readinessLevel")
            row["readiness_feedback"] = r.get("feedbackShort") or r.get("readinessFeedbackPhrase")
            row["acute_load"] = r.get("acuteLoad")
            row["hrv_weekly_avg"] = r.get("hrvWeeklyAverage")
    except Exception:
        pass
    time.sleep(API_DELAY)
    return row


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
                    acute_load, hrv_weekly_avg, synced_at)
                   VALUES
                   (:date, :readiness_score, :readiness_level, :readiness_feedback,
                    :acute_load, :hrv_weekly_avg, :synced_at)""",
                {k: row.get(k) for k in [
                    "date", "readiness_score", "readiness_level", "readiness_feedback",
                    "acute_load", "hrv_weekly_avg", "synced_at",
                ]},
            )
            conn.commit()
            count += 1
            progress.advance(task)
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
        since_health    = last_synced(conn, "health_daily", "date")
        since_training  = last_synced(conn, "training_daily", "date")
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
        ("activities",    "start_time_local"),
        ("health_daily",  "date"),
        ("training_daily","date"),
        ("weight",        "date"),
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
    rows = conn.execute("""
        SELECT date(start_time_local) as day,
               round(sum(distance_m)/1000, 1) as km,
               round(avg(avg_cadence), 0) as cadence,
               round(avg(avg_hr), 0) as avg_hr
        FROM activities
        WHERE activity_type LIKE '%running%'
          AND date(start_time_local) >= date('now', '-7 days')
        GROUP BY day ORDER BY day DESC
    """).fetchall()
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
                r["date"], str(r["hrv"] or "-"), r["hrv_status"] or "-",
                str(r["readiness"] or "-"), r["readiness_level"] or "-",
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
    for col in rows[0].keys():
        t.add_column(col)
    for row in rows:
        t.add_row(*[str(v) if v is not None else "—" for v in row])
    console.print(t)


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

    args = parser.parse_args()

    dispatch = {"sync": cmd_sync, "stats": cmd_stats, "query": cmd_query}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
