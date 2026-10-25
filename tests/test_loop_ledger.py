"""UNIT: kit.loop.ledger, over a temp runtime directory."""

import pytest

from kit.loop.ledger import LEDGER, StageEntry, StopEntry, append_entry, parse_entry, read_ledger
from kit.loop.stream import StageCost

COST = StageCost(1.5, 10, 2000, 50_000, 300, 60_000, 12, "sid-1")


def test_entries_round_trip_in_order(tmp_path):
    entries = [
        StageEntry("2026-10-20T09:00:00+02:00", "v0.3.0", "loop/a", "spec", "opus", "ok", COST),
        StageEntry("2026-10-20T09:01:00+02:00", "v0.3.0", "", "probe", "haiku", "error", None),
        StopEntry("2026-10-20T10:00:00+02:00", "v0.3.0", "limit"),
    ]
    for e in entries:
        append_entry(tmp_path / "rt", e)
    assert read_ledger(tmp_path / "rt") == entries


def test_missing_ledger_is_empty(tmp_path):
    assert read_ledger(tmp_path) == []


@pytest.mark.parametrize("line", ["", "not json", "[]", '{"kind": "other"}', '{"kind": "stop"}', '{"kind": "stage", "cost": 3}'])
def test_bad_lines_are_skipped(line):
    assert parse_entry(line) is None


def test_a_bad_line_does_not_hide_the_others(tmp_path):
    append_entry(tmp_path, StopEntry("t", "v", "done"))
    with (tmp_path / LEDGER).open("a") as f:
        f.write("garbage\n")
    append_entry(tmp_path, StopEntry("t", "v", "limit"))
    assert [e.reason for e in read_ledger(tmp_path)] == ["done", "limit"]
