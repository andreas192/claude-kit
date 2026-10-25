"""UNIT: kit.insights.loopstats, over ledger entries built in code."""

import math

from kit.bench.windows import Window
from kit.insights.loopstats import by_version, by_window, loop_session_ids, loop_stats
from kit.loop.ledger import StageEntry, StopEntry
from kit.loop.stream import StageCost

T = "2026-10-20T10:00:00+02:00"


def cost(usd: float, sid: str = "") -> StageCost:
    return StageCost(usd, 1, 1, 1, 1, 1000, 3, sid)


def stage(name: str, outcome: str = "ok", usd: float | None = 1.0, sid: str = "", time: str = T, version: str = "v0.3.0") -> StageEntry:
    return StageEntry(time, version, "loop/a", name, "sonnet", outcome, cost(usd, sid) if usd is not None else None)


ITEM = [
    stage("probe", usd=0.01),
    stage("spec", usd=3.0, sid="s1"),
    stage("plan", usd=1.0, sid="s2"),
    stage("build", "more", usd=2.0),
    stage("build", usd=2.0),
    stage("pr", usd=0.5),
    stage("spec", "park", usd=None),
    stage("build", "error", usd=0.49),
    StopEntry(T, "v0.3.0", "limit"),
    StopEntry(T, "v0.3.0", "crash"),
    StopEntry(T, "v0.3.0", "done"),
]


def test_loop_stats_counts_and_dollars():
    s = loop_stats(ITEM, {"s1": 90_000, "s2": 50_000})
    assert (s.runs, s.stages, s.shipped, s.parked, s.builds, s.errors, s.usage_stops, s.failed_runs) == (3, 7, 1, 1, 3, 1, 1, 1)
    assert s.usd["probe"] == 0.01 and s.usd["build"] == 4.49
    assert math.isclose(s.total_usd, 9.0)
    assert math.isclose(s.usd_per_shipped, 9.0) and s.builds_per_shipped == 3
    assert math.isclose(s.opus_share, 4 / 9)
    assert s.peak_k == 70.0 and s.finished == 2


def test_loop_stats_with_nothing_is_nan_not_an_error():
    s = loop_stats([], {})
    assert s.total_usd == 0 and all(math.isnan(v) for v in (s.usd_per_shipped, s.builds_per_shipped, s.opus_share, s.peak_k))


def test_by_window_uses_utc_and_drops_bad_or_outside_times():
    week = Window("W", "2026-10-19T00:00:00+00:00", "2026-10-26T00:00:00+00:00")
    early, bad = stage("spec", time="2026-10-19T01:59:59+02:00"), stage("spec", time="x")
    inside = stage("spec", time="2026-10-19T02:00:00+02:00")
    assert by_window([early, inside, bad], [week]) == {"W": [inside]}


def test_by_version_keeps_first_seen_order_and_names_blank_unknown():
    a, b, c = stage("spec", version="v0.3.0"), stage("spec", version=""), stage("pr", version="v0.3.0")
    assert by_version([a, b, c]) == {"v0.3.0": [a, c], "unknown": [b]}


def test_loop_session_ids_come_from_costed_stages():
    assert loop_session_ids(ITEM) == {"s1", "s2", ""}
