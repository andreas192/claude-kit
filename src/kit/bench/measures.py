"""Friction, quality and speed measures from transcripts (counts and ratios only, never message text)."""

from __future__ import annotations

import re
import statistics

from kit.bench.benchmarks import Benchmark, is_implementer, is_reviewer, task_count
from kit.bench.transcripts import Session, Subagent, Transcript
from kit.bench.windows import parse_utc

FINDING = re.compile(r"^\s*\d+\.\s", re.M)
RE_REVIEW = re.compile(r"re-?review", re.I)
NAN = float("nan")

NOT_MEASURED = ["permission prompts: approved prompts are not recorded in transcripts"]


def transcripts(session: Session) -> list[Transcript]:
    return [session.main] + [a.transcript for a in session.subagents]


def per_session(count: str, sessions: list[Session]) -> float:
    return sum(getattr(t, count) for s in sessions for t in transcripts(s)) / max(1, len(sessions))


def findings(reviewer: Subagent) -> int:
    text = reviewer.transcript.last_text
    return 0 if text.startswith("PASS") else len(FINDING.findall(text))


def implementers(session: Session) -> list[Subagent]:
    return [a for a in session.subagents if is_implementer(a)]


def implemented_tasks(session: Session) -> int:
    return sum(task_count(a.description) for a in implementers(session))


def executed(sessions: list[Session]) -> list[Session]:
    """Sessions with at least one implementer."""
    return [s for s in sessions if implementers(s)]


def minutes(session: Session) -> float | None:
    start, end = parse_utc(session.main.start), parse_utc(session.main.end)
    return None if start is None or end is None else (end - start).total_seconds() / 60


def m_permission_denials(sessions: list[Session]) -> float:
    return per_session("permission_denials", sessions)


def m_hook_denials(sessions: list[Session]) -> float:
    return per_session("hook_denials", sessions)


def m_context_warnings(sessions: list[Session]) -> float:
    return per_session("context_warnings", sessions)


def m_findings(sessions: list[Session]) -> float:
    reviewers = [a for s in sessions for a in s.subagents if is_reviewer(a)]
    return sum(findings(a) for a in reviewers) / len(reviewers) if reviewers else NAN


def m_rereviews(sessions: list[Session]) -> float:
    agents = [a for s in sessions for a in s.subagents]
    count = sum(1 for a in agents if is_reviewer(a) and RE_REVIEW.search(a.description))
    total = sum(1 for a in agents if is_implementer(a))
    return count / total if total else NAN


def m_failed_tests(sessions: list[Session]) -> float:
    runs = executed(sessions)
    tasks = sum(implemented_tasks(s) for s in runs)
    return sum(t.failed_test_runs for s in runs for t in transcripts(s)) / tasks if tasks else NAN


def m_duration(sessions: list[Session]) -> float:
    spans = [m for s in sessions if (m := minutes(s)) is not None]
    return statistics.median(spans) if spans else NAN


def m_owner_prompts(sessions: list[Session]) -> float:
    runs = executed(sessions)
    tasks = sum(implemented_tasks(s) for s in runs)
    return sum(s.main.prompts for s in runs) / tasks if tasks else NAN


MEASURES = [
    Benchmark("F1", "permission denials per session", "falls", m_permission_denials),
    Benchmark("F2", "hook denials per session", "falls", m_hook_denials),
    Benchmark("F3", "context-warn firings per session", "falls", m_context_warnings),
    Benchmark("Q1", "reviewer findings per reviewer", "falls", m_findings),
    Benchmark("Q2", "re-reviews per implementer", "falls", m_rereviews),
    Benchmark("Q3", "failed test runs per implemented task", "falls", m_failed_tests),
    Benchmark("S1", "session duration, median (min)", "falls", m_duration),
    Benchmark("S2", "owner prompts per implemented task", "falls", m_owner_prompts),
]
