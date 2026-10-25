"""UNIT: kit.insights.weeks."""

from datetime import date

from kit.bench.windows import Window
from kit.insights.weeks import applied_in, last_weeks, week_name


def test_week_name_uses_the_iso_year():
    assert week_name(date(2026, 10, 19)) == "2026-W43"
    assert week_name(date(2027, 1, 1)) == "2026-W53"


def test_last_weeks_are_complete_and_leave_out_this_week():
    weeks = last_weeks(date(2026, 10, 25), 2)  # a Sunday in W43
    assert weeks == [
        Window("2026-W41", "2026-10-05T00:00:00+00:00", "2026-10-12T00:00:00+00:00"),
        Window("2026-W42", "2026-10-12T00:00:00+00:00", "2026-10-19T00:00:00+00:00"),
    ]


def test_on_a_monday_last_week_is_the_newest():
    assert last_weeks(date(2026, 10, 26), 1)[0].name == "2026-W43"


def test_applied_in_names_versions_starting_in_the_week():
    week = last_weeks(date(2026, 10, 26), 1)[0]
    versions = [Window("pre-kit", "", "2026-10-20T00:00:00Z"), Window("v0.2.0", "2026-10-20T00:00:00Z", "2026-10-27T00:00:00Z"), Window("v0.3.0", "2026-10-27T00:00:00Z", "")]
    assert applied_in(week, versions) == ("v0.2.0",)
