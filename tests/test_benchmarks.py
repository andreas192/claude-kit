"""UNIT: kit.bench.benchmarks, over sessions built in code."""

import pytest
from builders import session

from kit.bench.benchmarks import (
    BENCHMARKS,
    b_over,
    b_peak,
    b_reviewers,
    b_search,
    b_startup,
    b_stray_opus,
    b_haiku_batch,
    cache_breaks,
    cost_per_task,
    fmt,
    is_implementer,
    is_reviewer,
    task_count,
)
from kit.bench.transcripts import Call, Subagent, Transcript


@pytest.mark.parametrize(
    ("description", "count"),
    [("Implement Task 3: debt", 1), ("Implement Tasks 3-5", 3), ("Tasks 2, 4 and 6", 3), ("Tasks 7–8", 2), ("Fix the window", 1)],
)
def test_task_count(description: str, count: int) -> None:
    assert task_count(description) == count


def test_cache_breaks_ignore_the_first_call() -> None:
    calls = [Call("opus", 0, 9000, 0, 1), Call("opus", 0, 100, 9000, 1), Call("opus", 0, 6000, 4000, 1)]
    assert cache_breaks(Transcript(calls=calls)) == 1


def test_peak_benchmarks() -> None:
    sessions = [session(50_000), session(90_000), session(130_000)]
    assert b_peak(sessions) == 90
    assert b_over(80_000)(sessions) == pytest.approx(200 / 3)
    assert b_over(120_000)(sessions) == pytest.approx(100 / 3)


def test_agent_benchmarks() -> None:
    s = session(
        1,
        [
            ("implementer-sonnet", "Implement Task 1", "sonnet"),
            ("implementer-haiku", "Implement Tasks 2-4", "haiku"),
            ("general-purpose", "Review Tasks 1-4", "sonnet"),
            ("general-purpose", "Review Task 5", "opus"),
            ("general-purpose", "Final whole-branch review", "opus"),
            ("Explore", "Find callers", "haiku"),
        ],
    )
    assert b_reviewers([s]) == 1.5
    assert b_stray_opus([s]) == 1
    assert b_haiku_batch([s]) == 3
    assert b_search([s]) == 1
    assert b_startup([s]) == pytest.approx(1.005)


def test_plugin_agents_are_classified_like_local_ones() -> None:
    agent = Subagent("kit:reviewer-sonnet", "Review batch 2", Transcript())
    assert is_reviewer(agent) and not is_implementer(agent)


def test_plugin_implementers_count_by_agent_type_alone() -> None:
    assert is_implementer(Subagent("kit:implementer-haiku", "Task 4", Transcript()))


def test_cost_per_task_needs_a_plan_run() -> None:
    few = session(1, [("implementer-sonnet", "Implement Task 1", "sonnet")] * 3)
    run = session(0, [("implementer-sonnet", "Implement Task 1", "sonnet")] * 3 + [("implementer-haiku", "Implement Tasks 2-3", "haiku")])
    assert cost_per_task(few) is None
    assert cost_per_task(run) == pytest.approx((5 * 1 + 4 * (5 + 1250 + 5)) / 5)


def test_benchmarks_are_b1_to_b13_in_order() -> None:
    assert [b.key for b in BENCHMARKS] == [f"B{n}" for n in range(1, 14)]


def test_b12_is_blank_without_a_plan_run() -> None:
    assert fmt(BENCHMARKS[11].measure([session(1)])) == "-"


@pytest.mark.parametrize(("value", "text"), [(float("nan"), "-"), (1234.4, "1,234"), (0.5, "0.50"), (12.0, "12")])
def test_fmt(value: float, text: str) -> None:
    assert fmt(value) == text
