"""ISO weeks in UTC as bench windows: the complete weeks before today, oldest first."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from kit.bench.windows import Window, contains, parse_utc


def week_name(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def utc_midnight(day: date) -> str:
    return datetime.combine(day, time(), timezone.utc).isoformat()


def last_weeks(today: date, count: int) -> list[Window]:
    """`count` complete weeks ending at the Monday of today's week; today's week is left out."""
    this_monday = monday_of(today)
    mondays = [this_monday - timedelta(weeks=n) for n in range(count, 0, -1)]
    return [Window(week_name(m), utc_midnight(m), utc_midnight(m + timedelta(weeks=1))) for m in mondays]


def applied_in(week: Window, versions: list[Window]) -> tuple[str, ...]:
    """The versions whose window starts inside `week` (the pre-kit window has no start and never counts)."""
    return tuple(v.name for v in versions if (start := parse_utc(v.start)) is not None and contains(week, start))
