"""UNIT: kit.bench.windows, grouping sessions by the kit version active at their first record."""

import pytest
from builders import session

from kit.bench.gitlog import Merge
from kit.bench.windows import assign, drop_before, fix_share, make_windows
from kit.errors import KitError

WINDOWS = make_windows([("v0.1.0", "2026-10-18T00:00:00Z"), ("v0.2.0", "2026-10-25T00:00:00Z")])


def test_windows_and_assignment_by_first_record():
    ws = WINDOWS
    assert [(w.name, w.start, w.end) for w in ws] == [("pre-kit", "", "2026-10-18T00:00:00Z"), ("v0.1.0", "2026-10-18T00:00:00Z", "2026-10-25T00:00:00Z"), ("v0.2.0", "2026-10-25T00:00:00Z", "")]
    spanning = session(start="2026-10-17T23:00:00Z", end="2026-10-18T02:00:00Z")
    assert assign([spanning, session(start="")], ws)["pre-kit"] == [spanning]


def test_no_applies_gives_one_open_pre_kit_window():
    assert [(w.name, w.start, w.end) for w in make_windows([])] == [("pre-kit", "", "")]


def test_boundaries_compare_as_times_not_strings():
    on_boundary = session(start="2026-10-18T00:00:00+00:00")
    offset = session(start="2026-10-18T01:00:00+02:00")  # 2026-10-17T23:00Z
    got = assign([on_boundary, offset], WINDOWS)
    assert got["v0.1.0"] == [on_boundary] and got["pre-kit"] == [offset]


def test_every_window_is_present_and_garbage_starts_are_dropped():
    got = assign([session(start="not a time")], WINDOWS)
    assert got == {"pre-kit": [], "v0.1.0": [], "v0.2.0": []}


def test_date_only_start_counts_as_utc_midnight():
    s = session(start="2026-10-19")
    assert assign([s], WINDOWS)["v0.1.0"] == [s]


def test_drop_before_keeps_sessions_starting_at_or_after_since():
    early, on, late = session(start="2026-10-17T23:59:59Z"), session(start="2026-10-18T00:00:00Z"), session(start="2026-10-19")
    assert drop_before([early, on, late, session(start="")], "2026-10-18T00:00:00Z") == [on, late]


def test_drop_before_without_since_keeps_everything():
    sessions = [session(start=""), session()]
    assert drop_before(sessions, "") == sessions


def test_drop_before_rejects_a_non_time():
    with pytest.raises(KitError, match="--since"):
        drop_before([session()], "yesterday")


def test_fix_share_counts_merges_in_the_window():
    ms = [Merge("1", "2026-10-17T10:00:00Z", "feat a", frozenset({"a"})),
          Merge("2", "2026-10-19T10:00:00Z", "feat b", frozenset({"b"})),
          Merge("3", "2026-10-19T11:00:00Z", "feat c", frozenset({"c"}))]
    flags = [True, True, False]
    assert fix_share(WINDOWS[1], ms, flags) == 0.5
    assert fix_share(WINDOWS[0], ms, flags) == 1.0


def test_fix_share_is_nan_without_merges_in_the_window():
    assert fix_share(WINDOWS[2], [], []) != fix_share(WINDOWS[2], [], [])
