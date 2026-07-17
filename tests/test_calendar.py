"""Tests for garmin_connect_cli.commands.calendar.

Pure/offline - build_calendar_days takes raw calendarItems and produces one
row per day, so no Garmin API is involved.
"""

from __future__ import annotations

from garmin_connect_cli.commands.calendar import _parse_month, build_calendar_days


class TestBuildCalendarDays:
    def test_emits_one_row_per_day_of_month(self) -> None:
        days = build_calendar_days([], 2026, 7)
        assert len(days) == 31
        assert days[0]["date"] == "2026-07-01"
        assert days[-1]["date"] == "2026-07-31"

    def test_february_length(self) -> None:
        assert len(build_calendar_days([], 2026, 2)) == 28  # non-leap
        assert len(build_calendar_days([], 2024, 2)) == 29  # leap

    def test_weekday_labels(self) -> None:
        days = build_calendar_days([], 2026, 7)
        # 2026-07-21 is a Tuesday
        row = next(d for d in days if d["date"] == "2026-07-21")
        assert row["weekday"] == "Tue"

    def test_splits_workouts_and_activities(self) -> None:
        items = [
            {"date": "2026-07-21", "itemType": "workout", "title": "Quality Session"},
            {"date": "2026-07-21", "itemType": "workout", "title": "Lower Body: PTT"},
            {"date": "2026-07-16", "itemType": "activity", "title": "Easy Run"},
        ]
        days = {d["date"]: d for d in build_calendar_days(items, 2026, 7)}
        assert days["2026-07-21"]["workouts"] == ["Lower Body: PTT", "Quality Session"]
        assert days["2026-07-21"]["activities"] == []
        assert days["2026-07-16"]["activities"] == ["Easy Run"]

    def test_dedupes_repeated_titles(self) -> None:
        items = [
            {"date": "2026-07-25", "itemType": "workout", "title": "Long Run"},
            {"date": "2026-07-25", "itemType": "workout", "title": "Long Run"},
        ]
        row = next(d for d in build_calendar_days(items, 2026, 7) if d["date"] == "2026-07-25")
        assert row["workouts"] == ["Long Run"]

    def test_ignores_items_outside_month(self) -> None:
        # build_calendar_days only walks the target month; a stray date is dropped
        items = [{"date": "2026-08-01", "itemType": "workout", "title": "Stray"}]
        days = build_calendar_days(items, 2026, 7)
        assert all("Stray" not in d["workouts"] for d in days)


class TestParseMonth:
    def test_parses_valid(self) -> None:
        assert _parse_month("2026-07") == (2026, 7)

    def test_defaults_to_current_month(self) -> None:
        import datetime

        y, m = _parse_month(None)
        today = datetime.date.today()
        assert (y, m) == (today.year, today.month)

    def test_rejects_bad_format(self) -> None:
        import pytest
        import typer

        with pytest.raises(typer.BadParameter):
            _parse_month("2026/07")

    def test_rejects_out_of_range_month(self) -> None:
        import pytest
        import typer

        with pytest.raises(typer.BadParameter):
            _parse_month("2026-13")
