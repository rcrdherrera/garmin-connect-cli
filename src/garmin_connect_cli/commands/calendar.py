"""Calendar view — scheduled workouts and completed activities, day by day.

The coaching skills (``/coach``, ``/evaluate``, ``/analyze``) use this to see the
run / strength / rest layout of a month so strength sessions can be placed around
run days instead of re-deriving the calendar with ad-hoc scripts each time.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date
from typing import Annotated, Any

import typer

from garmin_connect_cli.client import GarminClient
from garmin_connect_cli.core import emit, with_client

app = typer.Typer(no_args_is_help=False)

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def build_calendar_days(items: list[dict[str, Any]], year: int, month: int) -> list[dict[str, Any]]:
    """Turn raw Garmin calendarItems into one row per day of the month.

    Pure function (no I/O) so it can be unit-tested. Each row is::

        {"date": "2026-07-21", "weekday": "Tue",
         "workouts": ["Quality Session", "Lower Body: ..."],
         "activities": []}

    ``workouts`` are scheduled (planned) sessions; ``activities`` are completed.
    Both are de-duplicated and sorted for stable output.
    """
    by_date: dict[str, dict[str, set[str]]] = {}
    for it in items:
        d = it.get("date", "") or ""
        bucket = by_date.setdefault(d, {"workouts": set(), "activities": set()})
        title = (it.get("title") or "").strip()
        itype = it.get("itemType")
        if itype == "workout":
            bucket["workouts"].add(title)
        elif itype == "activity":
            bucket["activities"].add(title)

    ndays = _cal.monthrange(year, month)[1]
    days: list[dict[str, Any]] = []
    for dom in range(1, ndays + 1):
        d = date(year, month, dom)
        ds = d.isoformat()
        bucket = by_date.get(ds, {"workouts": set(), "activities": set()})
        days.append(
            {
                "date": ds,
                "weekday": _WEEKDAYS[d.weekday()],
                "workouts": sorted(bucket["workouts"]),
                "activities": sorted(bucket["activities"]),
            }
        )
    return days


def _parse_month(month: str | None) -> tuple[int, int]:
    """Parse a YYYY-MM string, defaulting to the current month."""
    if not month:
        today = date.today()
        return today.year, today.month
    try:
        y, m = month.split("-")
        year, mon = int(y), int(m)
    except (ValueError, AttributeError):
        raise typer.BadParameter("--month must be YYYY-MM, e.g. 2026-07") from None
    if not 1 <= mon <= 12:
        raise typer.BadParameter("--month must be YYYY-MM with month 01-12")
    return year, mon


@app.command("show")
@with_client
def show_calendar(
    client: GarminClient,
    month: Annotated[
        str | None,
        typer.Option("--month", "-m", help="Month as YYYY-MM (default: current month)"),
    ] = None,
) -> None:
    """Show the training calendar for a month, one row per day.

    Lists each day's scheduled workouts and completed activities — the run /
    strength / rest layout used to place strength sessions around run days.

    Examples:
        garmin-connect calendar show
        garmin-connect calendar show --month 2026-07
        garmin-connect --format table calendar show --month 2026-08
    """
    year, mon = _parse_month(month)
    items = client.get_calendar_month(year, mon)
    emit(build_calendar_days(items, year, mon))
