"""UNIT: kit.loop.schedule, the weekday gate, launchd hours and plist, and other loop agents."""

import plistlib
from datetime import datetime
from pathlib import Path

import pytest

from kit.loop.schedule import may_start, other_loop_agents, plist_xml, run_hours


@pytest.mark.parametrize(
    "day, ok",
    [("2026-10-23", True), ("2026-10-24", False), ("2026-10-25", False), ("2026-10-26", True)],
)
def test_may_start_on_weekdays_only(day, ok):
    assert may_start(datetime.fromisoformat(f"{day}T10:00")) is ok


def test_plist_has_weekday_hours_and_no_interval(tmp_path):
    xml = plist_xml(
        "com.kit.loop.dg",
        ["uv", "run"],
        {"PYTHONPATH": "/s/src"},
        tmp_path,
        tmp_path / "l.log",
        run_hours(5),
    )
    d = plistlib.loads(xml.encode())
    assert len(d["StartCalendarInterval"]) == 25
    assert {e["Weekday"] for e in d["StartCalendarInterval"]} == {1, 2, 3, 4, 5}
    assert {e["Hour"] for e in d["StartCalendarInterval"]} == {0, 5, 10, 15, 20}
    assert "StartInterval" not in d
    assert d["EnvironmentVariables"]["PYTHONPATH"] == "/s/src"
    assert d["RunAtLoad"] is False


def test_other_loop_agents_finds_the_old_dgi_agent(tmp_path):
    (tmp_path / "com.dgi.feature-loop.plist").write_text(
        "<string>/p/dividend-growth/data/loop/bin/feature_loop.py</string>"
    )
    (tmp_path / "com.kit.loop.dividend-growth.plist").write_text("/p/dividend-growth")
    assert other_loop_agents(
        tmp_path, Path("/p/dividend-growth"), "com.kit.loop.dividend-growth"
    ) == [tmp_path / "com.dgi.feature-loop.plist"]
