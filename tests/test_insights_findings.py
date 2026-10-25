"""UNIT: kit.insights.findings, over LoopStats and sessions built in code."""

from builders import session

from kit.insights.findings import Week, findings, rose
from kit.insights.loopstats import STAGES, LoopStats

NAN = float("nan")


def stats(**over) -> LoopStats:
    base = dict(runs=1, stages=4, shipped=1, parked=0, builds=1, errors=0, usage_stops=0, failed_runs=0, usd=dict.fromkeys(STAGES, 1.0), peak_k=40.0)
    return LoopStats(**{**base, **over})


def week(loop: LoopStats | None = None, sessions=(), applied=()) -> Week:
    return Week("W", loop or stats(), list(sessions), tuple(applied))


def keys(weeks: list[Week]) -> list[str]:
    return [f.key for f in findings(weeks)]


def test_a_healthy_week_has_no_findings():
    assert keys([week()]) == []
    assert findings([]) == []


def test_each_loop_rule_fires_on_its_own():
    opus = dict.fromkeys(STAGES, 0.0) | {"spec": 3.0, "plan": 1.0, "build": 1.0}
    assert keys([week(stats(usd=opus))]) == ["L1"]
    assert keys([week(stats(builds=4))]) == ["L2"]
    assert keys([week(stats(shipped=1, parked=1))]) == ["L3"]
    assert keys([week(stats(failed_runs=1))]) == ["L4"]
    assert keys([week(stats(usage_stops=2))]) == ["L5"]
    assert keys([week(stats(peak_k=81.0))]) == ["L7"]


def test_cost_regression_names_the_version_applied_that_week():
    cheap, dear = stats(), stats(usd=dict.fromkeys(STAGES, 1.3))
    found = findings([week(cheap), week(dear, applied=["v0.3.0"])])
    assert [f.key for f in found] == ["L6"] and "kit v0.3.0 took effect" in found[0].evidence


def test_session_rules_need_min_sessions():
    heavy = [session(peak=100_000) for _ in range(4)]
    assert keys([week(sessions=heavy)]) == []
    assert keys([week(sessions=[*heavy, session(peak=100_000)])]) == ["S1"]


def test_session_cost_regression_against_the_week_before():
    before = [session(peak=1000, prompts=1) for _ in range(5)]
    now = [session(peak=2000, prompts=1) for _ in range(5)]
    assert keys([week(sessions=before), week(sessions=now)]) == ["S6"]


def test_rose_ignores_missing_or_zero_baselines():
    assert rose(1.3, 1.0) and not rose(1.2, 1.0)
    assert not rose(5.0, 0.0) and not rose(NAN, 1.0) and not rose(1.0, NAN)
