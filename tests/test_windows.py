"""UNIT: kit.bench.windows, grouping sessions by the kit version active at their first record."""

from builders import session

from kit.bench.windows import assign, make_windows

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
