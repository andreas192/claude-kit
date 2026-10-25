"""Findings: fixed rules over the latest week's numbers, each with its evidence and one suggested change."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kit.bench.benchmarks import b_breaks, b_peak, b_prompt_cost, b_reviewers, b_stray_opus, fmt
from kit.bench.measures import m_permission_denials
from kit.bench.report import MIN_SESSIONS
from kit.bench.transcripts import Session
from kit.insights.loopstats import LoopStats

OPUS_SHARE_MAX = 0.5
BUILDS_PER_ITEM_MAX = 3
PARK_SHARE_MAX = 0.3
USAGE_STOPS_MAX = 2
REGRESSION = 0.25
PEAK_K_MAX = 80
SESSION_PEAK_K_MAX = 80
BREAKS_MAX = 2
REVIEWERS_MAX = 0.5
DENIALS_MAX = 1


@dataclass(frozen=True)
class Finding:
    key: str
    evidence: str
    suggestion: str


@dataclass(frozen=True)
class Week:
    name: str
    loop: LoopStats
    sessions: list[Session]
    applied: tuple[str, ...]  # kit versions that took effect in this week
    fix_share: float = float("nan")  # Q4 over the week's merges


def rose(now: float, before: float) -> bool:
    """True when `now` is over (1 + REGRESSION) x `before`; False when either is missing or `before` is 0."""
    return now == now and before == before and before > 0 and now > before * (1 + REGRESSION)


def applied_note(week: Week) -> str:
    return f"; kit {', '.join(week.applied)} took effect this week" if week.applied else ""


def loop_findings(now: Week, before: Week | None) -> list[Finding]:
    s, found = now.loop, []
    if s.opus_share == s.opus_share and s.opus_share > OPUS_SHARE_MAX:
        found.append(Finding("L1", f"spec + plan were {s.opus_share:.0%} of loop $", "try `plan` on Sonnet in STAGE_MODELS, or trim the spec prompt's read-first list"))
    if s.builds_per_shipped == s.builds_per_shipped and s.builds_per_shipped > BUILDS_PER_ITEM_MAX:
        found.append(Finding("L2", f"{fmt(s.builds_per_shipped)} build sessions per shipped item", "plans are too big for one build session; ask the plan stage for fewer, smaller tasks"))
    if s.finished and s.parked / s.finished > PARK_SHARE_MAX:
        found.append(Finding("L3", f"{s.parked} of {s.finished} finished items parked", "open roadmap items need more detail (scope, data source) before they reach `open`"))
    if s.errors or s.failed_runs:
        found.append(Finding("L4", f"{s.errors} stage errors, {s.failed_runs} failed runs", "read `kit loop status`; permission denials go in `.claude/loop-settings.json`"))
    if s.usage_stops >= USAGE_STOPS_MAX:
        found.append(Finding("L5", f"{s.usage_stops} runs stopped on usage", "raise `loop.interval_hours` so runs stop less often mid-item"))
    if before is not None and rose(s.usd_per_shipped, before.loop.usd_per_shipped):
        evidence = f"$ per shipped item {fmt(before.loop.usd_per_shipped)} -> {fmt(s.usd_per_shipped)}{applied_note(now)}"
        found.append(Finding("L6", evidence, "compare the stage $ columns with the week before to find the stage that grew"))
    if s.peak_k == s.peak_k and s.peak_k > PEAK_K_MAX:
        found.append(Finding("L7", f"median stage peak context {fmt(s.peak_k)}k", "stages read too much; shorten read-first lists or split the stage"))
    return found


SessionRule = tuple[str, Callable[[list[Session]], float], float, str, str]

SESSION_RULES: list[SessionRule] = [
    ("S1", b_peak, SESSION_PEAK_K_MAX, "median peak context {}k", "`/clear` between tasks; hand work to subagents"),
    ("S2", b_breaks, BREAKS_MAX, "{} cache breaks per session", "keep settings, model and tools fixed within a session"),
    ("S3", b_reviewers, REVIEWERS_MAX, "{} reviewers per implementer", "batch reviews: one reviewer per few tasks"),
    ("S4", b_stray_opus, 0, "{} Opus subagents outside a final review", "use kit:implementer-sonnet or -haiku"),
    ("S5", m_permission_denials, DENIALS_MAX, "{} permission denials per session", "run `/fewer-permission-prompts` in that repo"),
]


def session_findings(now: Week, before: Week | None) -> list[Finding]:
    if len(now.sessions) < MIN_SESSIONS:
        return []
    found = []
    for key, measure, limit, evidence, suggestion in SESSION_RULES:
        value = measure(now.sessions)
        if value == value and value > limit:
            found.append(Finding(key, evidence.format(fmt(value)), suggestion))
    if before is not None and len(before.sessions) >= MIN_SESSIONS:
        cost, earlier = b_prompt_cost(now.sessions), b_prompt_cost(before.sessions)
        if rose(cost, earlier):
            evidence = f"cost per prompt {fmt(earlier)}k -> {fmt(cost)}k{applied_note(now)}"
            found.append(Finding("S6", evidence, "check the S1-S5 rows of this week for the cause"))
    return found


def findings(weeks: list[Week]) -> list[Finding]:
    """Rules over the newest week, against the week before it."""
    if not weeks:
        return []
    now, before = weeks[-1], weeks[-2] if len(weeks) > 1 else None
    return loop_findings(now, before) + session_findings(now, before)
