"""UNIT: kit.bench.measures, over sessions built in code."""

import math

from builders import implementer, reviewer, session

from kit.bench.measures import MEASURES, NOT_MEASURED
from kit.bench.transcripts import Session, Subagent, Transcript


def measure(key: str, sessions: list[Session]) -> float:
    return next(m for m in MEASURES if m.key == key).measure(sessions)


def test_reviewer_findings_count_numbered_lines_and_pass_is_zero() -> None:
    s = session(subagents=[reviewer("Review batch 1", "1. a.py:3 x\n2. b.py:9 y"), reviewer("Review batch 2", "PASS")])
    assert measure("Q1", [s]) == 1.0


def test_rereviews_per_implementer() -> None:
    s = session(subagents=[implementer("Tasks 1-2"), implementer("Task 3"), reviewer("Re-review batch 1", "PASS")])
    assert measure("Q2", [s]) == 0.5


def test_failed_test_runs_per_implemented_task() -> None:
    s = session(subagents=[implementer("Tasks 1-2", failed_tests=3)])
    assert measure("Q3", [s]) == 1.5


def test_owner_prompts_per_implemented_task() -> None:
    s = session(subagents=[implementer("Tasks 1-2")], prompts=4)
    assert measure("S2", [s, session(prompts=50)]) == 2.0


def test_duration_is_median_minutes() -> None:
    assert measure("S1", [session(start="2026-10-17T07:00:00Z", end="2026-10-17T07:30:00Z")]) == 30.0


def test_duration_skips_sessions_without_timestamps() -> None:
    assert math.isnan(measure("S1", [session(start="", end="")]))


def test_ratios_are_nan_without_a_denominator() -> None:
    plain = [session()]
    assert all(math.isnan(measure(k, plain)) for k in ("Q1", "Q2", "Q3", "S2"))


def test_friction_counts_per_session_across_agents() -> None:
    a, b = session(), session()
    a.main.permission_denials, b.main.hook_denials, a.main.context_warnings = 3, 1, 2
    b.subagents.append(Subagent("x", "", Transcript(permission_denials=1)))
    assert (measure("F1", [a, b]), measure("F2", [a, b]), measure("F3", [a, b])) == (2.0, 0.5, 1.0)


def test_not_measured_names_permission_prompts() -> None:
    assert any(x.startswith("permission prompts") for x in NOT_MEASURED)
