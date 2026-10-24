"""The B1-B13 benchmarks (docs/token-strategy.md, "Benchmarks") over groups of sessions."""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass

from kit.bench.transcripts import Session, Subagent, Transcript, agent_kind

EXEC_MIN_IMPLEMENTERS = 4
BREAK_WRITE_SHARE = 0.5

REVIEW = re.compile(r"review", re.I)
IMPLEMENT = re.compile(r"implement", re.I)
FINAL = re.compile(r"final|whole[- ]branch", re.I)
SEARCH = re.compile(r"^(find|search|locate|explore|look for|where)\b", re.I)
TASK_REF = re.compile(r"tasks?\s+([\d\s,–\-&and]+)", re.I)


# ---- per-agent classification ----


def is_implementer(agent: Subagent) -> bool:
    return agent_kind(agent.agent_type).startswith("implementer") or bool(IMPLEMENT.search(agent.description))


def is_reviewer(agent: Subagent) -> bool:
    return "review" in agent_kind(agent.agent_type) or bool(REVIEW.search(agent.description))


def is_search(agent: Subagent) -> bool:
    return agent_kind(agent.agent_type) == "Explore" or bool(SEARCH.search(agent.description))


def task_count(description: str) -> int:
    """'Task 3' -> 1, 'Tasks 3-5' -> 3, 'Tasks 2, 4 and 6' -> 3; no task reference -> 1."""
    match = TASK_REF.search(description)
    if not match:
        return 1
    total = 0
    for part in re.split(r",|&|\band\b", match.group(1)):
        bounds = [int(n) for n in re.findall(r"\d+", part)]
        if len(bounds) == 2 and bounds[1] >= bounds[0]:
            total += bounds[1] - bounds[0] + 1
        else:
            total += len(bounds)
    return max(total, 1)


# ---- per-session measures ----


def peak_context(transcript: Transcript) -> int:
    return max((c.context for c in transcript.calls), default=0)


def read_per_output(transcript: Transcript) -> float:
    return sum(c.read for c in transcript.calls) / max(1, sum(c.output for c in transcript.calls))


def cache_breaks(transcript: Transcript) -> int:
    """Calls after the first whose cache write is over half the prompt: a cache miss."""
    return sum(1 for c in transcript.calls[1:] if c.context and c.write / c.context > BREAK_WRITE_SHARE)


def session_cost(session: Session) -> float:
    agents = sum(c.cost for a in session.subagents for c in a.transcript.calls)
    return sum(c.cost for c in session.main.calls) + agents


def cost_per_task(session: Session) -> float | None:
    """Total cost of a plan-execution session divided by implemented tasks; None if not one."""
    implementers = [a for a in session.subagents if is_implementer(a)]
    if len(implementers) < EXEC_MIN_IMPLEMENTERS:
        return None
    return session_cost(session) / sum(task_count(a.description) for a in implementers)


# ---- benchmarks over a group of sessions ----


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def share(flags: list[bool]) -> float:
    return 100 * sum(flags) / len(flags) if flags else 0.0


def all_agents(sessions: list[Session]) -> list[Subagent]:
    return [a for s in sessions for a in s.subagents]


def b_peak(sessions: list[Session]) -> float:
    return median([peak_context(s.main) / 1000 for s in sessions])


def b_over(limit: int) -> Callable[[list[Session]], float]:
    return lambda sessions: share([peak_context(s.main) > limit for s in sessions])


def b_read_ratio(sessions: list[Session]) -> float:
    return median([read_per_output(s.main) for s in sessions])


def b_breaks(sessions: list[Session]) -> float:
    return sum(cache_breaks(s.main) for s in sessions) / max(1, len(sessions))


def b_big_results(sessions: list[Session]) -> float:
    transcripts = [s.main for s in sessions] + [a.transcript for a in all_agents(sessions)]
    return sum(t.big_results for t in transcripts) / max(1, len(transcripts))


def b_startup(sessions: list[Session]) -> float:
    firsts = [a.transcript.calls[0] for a in all_agents(sessions) if is_implementer(a) and a.transcript.calls]
    return median([(c.fresh + c.write) / 1000 for c in firsts])


def b_reviewers(sessions: list[Session]) -> float:
    agents = all_agents(sessions)
    implementers = sum(1 for a in agents if is_implementer(a))
    return sum(1 for a in agents if is_reviewer(a)) / max(1, implementers)


def b_stray_opus(sessions: list[Session]) -> float:
    return sum(1 for a in all_agents(sessions) if a.model == "opus" and not FINAL.search(a.description))


def b_haiku_batch(sessions: list[Session]) -> float:
    haiku = [a for a in all_agents(sessions) if is_implementer(a) and a.model == "haiku"]
    return sum(task_count(a.description) for a in haiku) / len(haiku) if haiku else float("nan")


def b_search(sessions: list[Session]) -> float:
    return sum(1 for a in all_agents(sessions) if is_search(a)) / max(1, len(sessions))


def b_task_cost(sessions: list[Session]) -> float:
    costs = [c for s in sessions if (c := cost_per_task(s)) is not None]
    return median([c / 1000 for c in costs]) if costs else float("nan")


def b_prompt_cost(sessions: list[Session]) -> float:
    prompts = sum(s.main.prompts for s in sessions)
    return sum(session_cost(s) for s in sessions) / max(1, prompts) / 1000


@dataclass(frozen=True)
class Benchmark:
    key: str
    label: str
    target: str
    measure: Callable[[list[Session]], float]


BENCHMARKS = [
    Benchmark("B1", "median peak context (k)", "< 80", b_peak),
    Benchmark("B2", "% sessions over 80k", "falls", b_over(80_000)),
    Benchmark("B3", "% sessions over 120k", "<= 10", b_over(120_000)),
    Benchmark("B4", "median cache read / output", "-1/3 of base", b_read_ratio),
    Benchmark("B5", "cache breaks per session", "<= 2", b_breaks),
    Benchmark("B6", "tool results > 20k chars per transcript", "< 1", b_big_results),
    Benchmark("B7", "implementer startup write, median (k)", "falls", b_startup),
    Benchmark("B8", "reviewers per implementer", "<= 0.5", b_reviewers),
    Benchmark("B9", "Opus subagents, not a final review", "0", b_stray_opus),
    Benchmark("B10", "tasks per Haiku implementer", ">= 2", b_haiku_batch),
    Benchmark("B11", "search subagents per session", "few", b_search),
    Benchmark("B12", "cost per implemented task, median (k)", "falls", b_task_cost),
    Benchmark("B13", "cost per user prompt (k)", "falls", b_prompt_cost),
]


# ---- output ----


def fmt(value: float) -> str:
    if value != value:  # NaN: nothing to measure
        return "-"
    return f"{value:,.0f}" if abs(value) >= 10 else f"{value:.2f}"
