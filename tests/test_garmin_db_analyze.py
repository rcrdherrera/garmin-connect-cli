"""Tests for garmin_db.py's compute_period_analysis / analyze subcommand.

First test coverage for garmin_db.py. Uses a temp SQLite file (never the real
garmin.db), seeded with hand-computed fixture rows so every aggregate can be
asserted exactly.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

import garmin_db


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.executescript(garmin_db.SCHEMA)
    yield c
    c.close()


def _insert_health(conn, date_str, **kwargs):
    row = {
        "date": date_str,
        "hrv_last_night_avg": None,
        "hrv_weekly_avg": None,
        "hrv_status": None,
        "hrv_baseline_low": None,
        "hrv_baseline_high": None,
        "sleep_score": None,
        "sleep_duration_s": None,
        "sleep_deep_s": None,
        "sleep_rem_s": None,
        "sleep_light_s": None,
        "sleep_awake_s": None,
        "rhr": None,
        "body_battery_high": None,
        "body_battery_low": None,
        "stress": None,
        "synced_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(kwargs)
    cols = ",".join(row.keys())
    placeholders = ",".join(f":{k}" for k in row)
    conn.execute(f"INSERT INTO health_daily ({cols}) VALUES ({placeholders})", row)


def _insert_training(conn, date_str, **kwargs):
    row = {
        "date": date_str,
        "readiness_score": None,
        "readiness_level": None,
        "readiness_feedback": None,
        "acute_load": None,
        "hrv_weekly_avg": None,
        "training_status": None,
        "synced_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(kwargs)
    cols = ",".join(row.keys())
    placeholders = ",".join(f":{k}" for k in row)
    conn.execute(f"INSERT INTO training_daily ({cols}) VALUES ({placeholders})", row)


def _insert_activity(conn, activity_id, start_time_local, activity_type, **kwargs):
    row = {
        "activity_id": activity_id,
        "start_time_gmt": start_time_local,
        "start_time_local": start_time_local,
        "activity_name": "test",
        "activity_type": activity_type,
        "distance_m": None,
        "duration_s": None,
        "moving_time_s": None,
        "avg_hr": None,
        "max_hr": None,
        "avg_cadence": None,
        "max_cadence": None,
        "avg_speed_ms": None,
        "calories": None,
        "aerobic_te": None,
        "anaerobic_te": None,
        "training_load": None,
        "avg_gct_ms": None,
        "avg_stride_m": None,
        "avg_vert_osc_mm": None,
        "hr_z1_s": None,
        "hr_z2_s": None,
        "hr_z3_s": None,
        "hr_z4_s": None,
        "hr_z5_s": None,
        "raw_json": "{}",
        "synced_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(kwargs)
    cols = ",".join(row.keys())
    placeholders = ",".join(f":{k}" for k in row)
    conn.execute(f"INSERT INTO activities ({cols}) VALUES ({placeholders})", row)


class TestSleepMetrics:
    def test_averages_and_thresholds(self, conn):
        # 3 nights: 8h/90min deep (good), 6h/40min deep + score 65 (poor), 7.5h/80min deep
        _insert_health(
            conn,
            "2026-06-01",
            sleep_score=85,
            sleep_duration_s=8 * 3600,
            sleep_deep_s=90 * 60,
            sleep_rem_s=100 * 60,
            sleep_awake_s=20 * 60,
        )
        _insert_health(
            conn,
            "2026-06-02",
            sleep_score=65,
            sleep_duration_s=6 * 3600,
            sleep_deep_s=40 * 60,
            sleep_rem_s=60 * 60,
            sleep_awake_s=30 * 60,
        )
        _insert_health(
            conn,
            "2026-06-03",
            sleep_score=80,
            sleep_duration_s=7.5 * 3600,
            sleep_deep_s=80 * 60,
            sleep_rem_s=90 * 60,
            sleep_awake_s=25 * 60,
        )
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 3), metrics={"sleep"}
        )
        sleep = result["sleep"]
        assert sleep["n_nights"] == 3
        assert sleep["avg_sleep_score"] == pytest.approx((85 + 65 + 80) / 3)
        assert sleep["nights_below_7h"] == 1  # only the 6h night
        assert sleep["nights_score_under_70"] == 1  # only the 65 score
        assert sleep["avg_deep_h"] == pytest.approx((90 + 40 + 80) / 60 / 3)


class TestHrvMetrics:
    def test_avg_min_max_std_and_status_counts(self, conn):
        _insert_health(conn, "2026-06-01", hrv_last_night_avg=90, hrv_status="BALANCED")
        _insert_health(
            conn, "2026-06-02", hrv_last_night_avg=70, hrv_status="LOW", hrv_baseline_low=85
        )
        _insert_health(conn, "2026-06-03", hrv_last_night_avg=95, hrv_status="BALANCED")
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 3), metrics={"hrv"}
        )
        hrv = result["hrv"]
        assert hrv["avg_hrv"] == pytest.approx((90 + 70 + 95) / 3)
        assert hrv["min_hrv"] == 70
        assert hrv["max_hrv"] == 95
        assert hrv["status_counts"] == {"BALANCED": 2, "LOW": 1}
        # 70 < baseline_low(85) - 5 = 80 -> flagged as a stress day
        assert hrv["stress_flag_days"] == ["2026-06-02"]

    def test_empty_period_does_not_crash(self, conn):
        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 3), metrics={"hrv"}
        )
        hrv = result["hrv"]
        assert hrv["avg_hrv"] is None
        assert hrv["hrv_std"] is None
        assert hrv["status_counts"] == {}


class TestReadinessMetrics:
    def test_level_counts_and_acute_load(self, conn):
        _insert_training(
            conn, "2026-06-01", readiness_score=85, readiness_level="PRIME", acute_load=300
        )
        _insert_training(
            conn, "2026-06-02", readiness_score=30, readiness_level="RECOVERY", acute_load=500
        )
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 2), metrics={"readiness"}
        )
        readiness = result["readiness"]
        assert readiness["avg_readiness"] == pytest.approx(57.5)
        assert readiness["min_readiness"] == 30
        assert readiness["max_readiness"] == 85
        assert readiness["level_counts"] == {"PRIME": 1, "RECOVERY": 1}
        assert readiness["avg_acute_load"] == pytest.approx(400)


class TestRunningMetrics:
    def test_hr_zone_pct_and_cadence_buckets(self, conn):
        _insert_activity(
            conn,
            1,
            "2026-06-01 08:00:00",
            "running",
            distance_m=10000,
            duration_s=3600,
            avg_hr=150,
            avg_cadence=162,
            training_load=100,
            aerobic_te=3.5,
            hr_z1_s=100,
            hr_z2_s=200,
            hr_z3_s=50,
            hr_z4_s=0,
            hr_z5_s=0,
        )
        _insert_activity(
            conn,
            2,
            "2026-06-03 08:00:00",
            "treadmill_running",
            distance_m=5000,
            duration_s=1800,
            avg_hr=140,
            avg_cadence=148,
            training_load=50,
            aerobic_te=2.5,
            hr_z1_s=50,
            hr_z2_s=50,
            hr_z3_s=0,
            hr_z4_s=0,
            hr_z5_s=0,
        )
        # non-running activity must be excluded
        _insert_activity(conn, 3, "2026-06-02 08:00:00", "strength_training", training_load=20)
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 3), metrics={"running"}
        )
        running = result["running"]
        assert running["total_runs"] == 2
        assert running["total_km"] == pytest.approx(15.0)
        assert running["cadence_distribution"]["<150"] == 1
        assert running["cadence_distribution"]["160-164"] == 1
        # zone totals: z1=150, z2=250, z3=50, total=450
        assert running["hr_zone_pct"]["z1_pct"] == pytest.approx(150 / 450 * 100)
        assert running["longest_run_km"] == pytest.approx(10.0)
        assert running["hardest_load_session"] == 100

    def test_gct_balance_averages_only_runs_with_data(self, conn):
        # Two runs with chest-strap balance, one wrist run without it.
        _insert_activity(
            conn,
            1,
            "2026-06-01 08:00:00",
            "running",
            distance_m=10000,
            duration_s=3600,
            avg_gct_balance_left=50.2,
        )
        _insert_activity(
            conn,
            2,
            "2026-06-03 08:00:00",
            "running",
            distance_m=8000,
            duration_s=2880,
            avg_gct_balance_left=49.8,
        )
        _insert_activity(
            conn,
            3,
            "2026-06-05 08:00:00",
            "running",
            distance_m=5000,
            duration_s=1800,
            avg_gct_balance_left=None,
        )
        conn.commit()
        running = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 5), metrics={"running"}
        )["running"]
        assert running["n_runs_with_balance"] == 2
        assert running["avg_gct_balance_left"] == pytest.approx(50.0)


class TestStrengthMetrics:
    def test_counts_and_loads(self, conn):
        _insert_activity(conn, 1, "2026-06-01 08:00:00", "strength_training", training_load=30)
        _insert_activity(conn, 2, "2026-06-02 08:00:00", "strength_training", training_load=50)
        _insert_activity(conn, 3, "2026-06-03 08:00:00", "running", training_load=100)
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 3), metrics={"strength"}
        )
        strength = result["strength"]
        assert strength["total_strength_sessions"] == 2
        assert strength["avg_load"] == pytest.approx(40)
        assert strength["total_load"] == pytest.approx(80)


class TestBodyBatteryMetrics:
    def test_avg_and_low_day_count(self, conn):
        _insert_health(conn, "2026-06-01", body_battery_high=90, body_battery_low=20)
        _insert_health(conn, "2026-06-02", body_battery_high=55, body_battery_low=10)
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 2), metrics={"body_battery"}
        )
        bb = result["body_battery"]
        assert bb["avg_daily_high"] == pytest.approx(72.5)
        assert bb["days_high_below_60"] == 1


class TestNoBloatFields:
    def test_daily_rows_exclude_raw_json_and_synced_at(self, conn):
        # raw_json is the entire raw Garmin API payload per activity (~1,500 tokens
        # each) - nothing downstream reads it and it must never leak into results.
        _insert_health(conn, "2026-06-01", sleep_score=80)
        _insert_training(conn, "2026-06-01", readiness_score=70)
        _insert_activity(conn, 1, "2026-06-01 08:00:00", "running", raw_json='{"huge": "payload"}')
        conn.commit()

        result = garmin_db.compute_period_analysis(conn, date(2026, 6, 1), date(2026, 6, 1))
        for group in ("health", "training", "activities"):
            for row in result["daily_rows"][group]:
                assert "raw_json" not in row
                assert "synced_at" not in row


class TestCorrelations:
    def test_below_threshold_n_returns_none(self, conn):
        for i in range(1, 4):
            _insert_health(conn, f"2026-06-{i:02d}", hrv_last_night_avg=80 + i)
            _insert_training(conn, f"2026-06-{i:02d}", readiness_score=50 + i)
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 4), metrics={"correlations"}
        )
        corr = result["correlations"]["hrv_vs_next_day_readiness"]
        assert corr["r"] is None  # N < 7

    def test_perfect_correlation_with_enough_points(self, conn):
        # HRV today perfectly predicts (identical to) readiness tomorrow, 8 pairs
        for i in range(1, 10):
            hrv = 70 + i
            _insert_health(conn, f"2026-06-{i:02d}", hrv_last_night_avg=hrv)
            _insert_training(conn, f"2026-06-{i:02d}", readiness_score=hrv)
        conn.commit()

        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 9), metrics={"correlations"}
        )
        corr = result["correlations"]["hrv_vs_next_day_readiness"]
        assert corr["n"] == 8  # 9 days of HRV, 8 have a next-day readiness row
        assert corr["r"] == pytest.approx(1.0)


class TestPeriodResolution:
    def test_blank_is_last_7_days(self):
        today = date(2026, 7, 6)
        start, end = garmin_db._resolve_period(None, today)
        assert (start, end) == (date(2026, 6, 30), date(2026, 7, 6))

    def test_week_is_monday_to_today(self):
        today = date(2026, 7, 6)  # a Monday
        start, end = garmin_db._resolve_period("week", today)
        assert (start, end) == (date(2026, 7, 6), date(2026, 7, 6))

    def test_last_week_is_previous_full_week(self):
        today = date(2026, 7, 6)  # Monday
        start, end = garmin_db._resolve_period("last-week", today)
        assert (start, end) == (date(2026, 6, 29), date(2026, 7, 5))

    def test_month_and_last_month(self):
        today = date(2026, 7, 6)
        assert garmin_db._resolve_period("month", today) == (date(2026, 7, 1), today)
        assert garmin_db._resolve_period("last-month", today) == (
            date(2026, 6, 1),
            date(2026, 6, 30),
        )

    def test_explicit_year_and_month(self):
        assert garmin_db._resolve_period("2025", date(2026, 1, 1)) == (
            date(2025, 1, 1),
            date(2025, 12, 31),
        )
        assert garmin_db._resolve_period("2025-11", date(2026, 1, 1)) == (
            date(2025, 11, 1),
            date(2025, 11, 30),
        )
        assert garmin_db._resolve_period("2025-12", date(2026, 1, 1)) == (
            date(2025, 12, 1),
            date(2025, 12, 31),
        )

    def test_unrecognized_period_raises(self):
        with pytest.raises(ValueError):
            garmin_db._resolve_period("bogus", date(2026, 1, 1))

    def test_explicit_range(self):
        assert garmin_db._resolve_period("2025-08-01:2025-10-31", date(2026, 1, 1)) == (
            date(2025, 8, 1),
            date(2025, 10, 31),
        )

    def test_explicit_range_strips_whitespace(self):
        assert garmin_db._resolve_period("2025-08-01 : 2025-10-31", date(2026, 1, 1)) == (
            date(2025, 8, 1),
            date(2025, 10, 31),
        )

    def test_bare_single_day(self):
        d = date(2026, 5, 20)
        assert garmin_db._resolve_period("2026-05-20", date(2026, 7, 1)) == (d, d)

    def test_malformed_range_raises(self):
        with pytest.raises(ValueError):
            garmin_db._resolve_period("2026-13-01:2026-01-05", date(2026, 1, 1))

    def test_malformed_single_day_raises(self):
        with pytest.raises(ValueError):
            garmin_db._resolve_period("2026-13-01", date(2026, 1, 1))


class TestFlagOutlierDays:
    def test_flags_low_hrv_status(self, conn):
        health = [{"date": "2026-06-01", "hrv_status": "LOW", "body_battery_high": None}]
        assert garmin_db.flag_outlier_days(health, []) == [
            {"date": "2026-06-01", "hrv_status": "LOW"}
        ]

    def test_flags_low_readiness(self, conn):
        training = [{"date": "2026-06-01", "readiness_score": 25}]
        assert garmin_db.flag_outlier_days([], training) == [
            {"date": "2026-06-01", "readiness_score": 25}
        ]

    def test_flags_all_systems_stress(self, conn):
        health = [{"date": "2026-06-01", "hrv_status": "LOW", "body_battery_high": 50}]
        training = [{"date": "2026-06-01", "readiness_score": 30}]
        result = garmin_db.flag_outlier_days(health, training)
        assert len(result) == 1
        assert result[0]["all_systems_stress"] is True
        assert result[0]["hrv_status"] == "LOW"
        assert result[0]["readiness_score"] == 30

    def test_normal_day_not_flagged(self, conn):
        health = [{"date": "2026-06-01", "hrv_status": "BALANCED", "body_battery_high": 85}]
        training = [{"date": "2026-06-01", "readiness_score": 75}]
        assert garmin_db.flag_outlier_days(health, training) == []

    def test_sorted_by_date(self, conn):
        health = [
            {"date": "2026-06-03", "hrv_status": "LOW", "body_battery_high": None},
            {"date": "2026-06-01", "hrv_status": "LOW", "body_battery_high": None},
        ]
        result = garmin_db.flag_outlier_days(health, [])
        assert [r["date"] for r in result] == ["2026-06-01", "2026-06-03"]


class TestComputePeriodAnalysis:
    def test_unknown_metric_raises(self, conn):
        with pytest.raises(ValueError):
            garmin_db.compute_period_analysis(
                conn, date(2026, 6, 1), date(2026, 6, 2), metrics={"nonsense"}
            )

    def test_weekly_subtotals_only_for_28_plus_days(self, conn):
        result_short = garmin_db.compute_period_analysis(conn, date(2026, 6, 1), date(2026, 6, 10))
        assert result_short["weekly_subtotals"] is None

        result_long = garmin_db.compute_period_analysis(conn, date(2026, 6, 1), date(2026, 6, 30))
        assert result_long["weekly_subtotals"] is not None

    def test_daily_rows_always_included(self, conn):
        _insert_health(conn, "2026-06-01", sleep_score=80)
        conn.commit()
        result = garmin_db.compute_period_analysis(
            conn, date(2026, 6, 1), date(2026, 6, 1), metrics={"sleep"}
        )
        assert len(result["daily_rows"]["health"]) == 1
        assert result["daily_rows"]["health"][0]["sleep_score"] == 80


class TestSummarizeActivity:
    def test_zone_split_pace_and_cadence(self, conn):
        _insert_activity(
            conn,
            1,
            "2026-06-01 08:00:00",
            "running",
            activity_name="Test Run",
            distance_m=10000,
            duration_s=3000,  # 50 min -> 5:00/km
            avg_hr=150,
            max_hr=175,
            avg_cadence=165.4,
            aerobic_te=3.5,
            training_load=100,
            hr_z1_s=0,
            hr_z2_s=600,
            hr_z3_s=300,
            hr_z4_s=60,
            hr_z5_s=40,  # total 1000
        )
        conn.commit()
        s = garmin_db.summarize_activity(conn, 1)
        assert s["distance_km"] == 10.0
        assert s["duration_min"] == 50.0
        assert s["avg_pace_min_per_km"] == 5.0
        assert s["avg_cadence"] == 165.4
        assert s["hr_zone_pct"]["z2_pct"] == 60.0
        assert s["hr_zone_pct"]["z3_pct"] == 30.0
        assert s["hr_z3plus_pct"] == 40.0  # (300+60+40)/1000

    def test_gct_balance_surfaced_when_present(self, conn):
        _insert_activity(
            conn,
            1,
            "2026-06-01 08:00:00",
            "running",
            distance_m=10000,
            duration_s=3000,
            avg_gct_balance_left=50.2,
        )
        conn.commit()
        assert garmin_db.summarize_activity(conn, 1)["avg_gct_balance_left"] == 50.2

    def test_gct_balance_none_on_wrist_runs(self, conn):
        _insert_activity(
            conn, 1, "2026-06-01 08:00:00", "running", distance_m=10000, duration_s=3000
        )
        conn.commit()
        assert garmin_db.summarize_activity(conn, 1)["avg_gct_balance_left"] is None

    def test_missing_activity_returns_none(self, conn):
        assert garmin_db.summarize_activity(conn, 999) is None

    def test_zero_distance_does_not_crash(self, conn):
        _insert_activity(conn, 1, "2026-06-01 08:00:00", "strength_training", training_load=30)
        conn.commit()
        s = garmin_db.summarize_activity(conn, 1)
        assert s["avg_pace_min_per_km"] is None
        assert s["hr_zone_pct"]["z1_pct"] is None
        assert s["hr_z3plus_pct"] is None


class TestFindLatestRun:
    def test_picks_most_recent_run_ignoring_strength(self, conn):
        _insert_activity(conn, 1, "2026-06-01 08:00:00", "running")
        _insert_activity(conn, 2, "2026-06-03 08:00:00", "running")
        _insert_activity(conn, 3, "2026-06-05 08:00:00", "strength_training")
        conn.commit()
        assert garmin_db.find_latest_run(conn) == 2  # 06-03, not the 06-05 strength

    def test_as_of_filter(self, conn):
        _insert_activity(conn, 1, "2026-06-01 08:00:00", "running")
        _insert_activity(conn, 2, "2026-06-03 08:00:00", "running")
        conn.commit()
        assert garmin_db.find_latest_run(conn, as_of=date(2026, 6, 2)) == 1

    def test_no_runs_returns_none(self, conn):
        _insert_activity(conn, 1, "2026-06-01 08:00:00", "strength_training")
        conn.commit()
        assert garmin_db.find_latest_run(conn) is None


class TestLoadMetrics:
    def test_acwr_run_only_windows(self, conn):
        # acute (7d ending 06-30): only the 06-28 run (load 100)
        # chronic (28d ending 06-30): 06-28 (100) + 06-10 (200) = 300, weekly = 75
        # the 05-01 run is outside both windows
        _insert_activity(conn, 1, "2026-06-28 08:00:00", "running", training_load=100)
        _insert_activity(conn, 2, "2026-06-10 08:00:00", "running", training_load=200)
        _insert_activity(conn, 3, "2026-05-01 08:00:00", "running", training_load=999)
        conn.commit()
        m = garmin_db.compute_load_metrics(conn, date(2026, 6, 30))
        assert m["acute_load"] == 100
        assert m["chronic_load_weekly_avg"] == 75.0
        assert m["acwr"] == round(100 / 75, 2)  # 1.33

    def test_ctl_atl_single_impulse(self, conn):
        # Single load of 42 on the as_of day, tiny warmup -> exact EWMA:
        # ctl = 42 * (1/42) = 1.0 ; atl = 42 * (1/7) = 6.0 ; tsb = -5.0
        _insert_activity(conn, 1, "2026-06-30 08:00:00", "running", training_load=42)
        conn.commit()
        m = garmin_db.compute_load_metrics(conn, date(2026, 6, 30), warmup_days=2)
        assert m["ctl"] == 1.0
        assert m["atl"] == 6.0
        assert m["tsb"] == -5.0

    def test_strength_counts_for_load_but_not_acwr(self, conn):
        # A strength session on the as_of day: feeds CTL/ATL (LOAD_TYPES) but ACWR
        # is run-only, so acute run load is 0 and ACWR is undefined.
        _insert_activity(conn, 1, "2026-06-30 08:00:00", "strength_training", training_load=42)
        conn.commit()
        m = garmin_db.compute_load_metrics(conn, date(2026, 6, 30), warmup_days=0)
        assert m["ctl"] == 1.0
        assert m["atl"] == 6.0
        assert m["acute_load"] == 0.0
        assert m["acwr"] is None

    def test_decay_on_rest_day(self, conn):
        # Load 42 on 06-29, rest on 06-30. atl decays 6.0 -> 6.0*(6/7)=5.14 -> 5.1
        _insert_activity(conn, 1, "2026-06-29 08:00:00", "running", training_load=42)
        conn.commit()
        m = garmin_db.compute_load_metrics(conn, date(2026, 6, 30), warmup_days=1)
        assert m["atl"] == 5.1
        assert m["ctl"] == 1.0  # 1.0*(41/42) = 0.976 -> rounds to 1.0

    def test_empty_db_no_crash(self, conn):
        m = garmin_db.compute_load_metrics(conn, date(2026, 6, 30))
        assert m["acwr"] is None
        assert m["ctl"] == 0.0
        assert m["tsb"] == 0.0
