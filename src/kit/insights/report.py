"""The insights markdown: loop and session tables per week and per version, then findings. Numbers only."""

from __future__ import annotations

from kit.bench.benchmarks import BENCHMARKS, Benchmark, fmt
from kit.bench.measures import MEASURES
from kit.bench.report import Column, report_lines, row_line
from kit.insights.findings import Finding, Week
from kit.insights.loopstats import STAGES, LoopStats

SESSION_KEYS = ("B1", "B3", "B4", "B5", "B8", "B9", "B13", "F1", "F2", "S1", "S2")
SESSION_MEASURES = [m for m in [*BENCHMARKS, *MEASURES] if m.key in SESSION_KEYS]

LOOP_ROWS: list[tuple[str, str]] = [
    ("runs", "runs"),
    ("stages", "stage sessions"),
    ("shipped", "shipped (pr ok)"),
    ("parked", "parked"),
    ("builds_per_shipped", "build sessions per shipped item"),
    ("errors", "stage errors"),
    ("usage_stops", "stops on usage"),
    ("failed_runs", "failed runs"),
    *((f"usd:{s}", f"$ {s}") for s in STAGES),
    ("total_usd", "$ total"),
    ("usd_per_shipped", "$ per shipped item"),
    ("opus_share", "spec + plan share of $"),
    ("peak_k", "stage peak context, median (k)"),
]


def loop_value(stats: LoopStats, field: str) -> str:
    if field.startswith("usd:"):
        return f"{stats.usd[field[4:]]:.2f}"
    value = getattr(stats, field)
    if field in ("total_usd", "usd_per_shipped"):
        return "-" if value != value else f"{value:.2f}"
    if field == "opus_share":
        return "-" if value != value else f"{value:.0%}"
    return str(value) if isinstance(value, int) else fmt(value)


def loop_table(columns: list[tuple[str, LoopStats]]) -> list[str]:
    head = ["loop", *(name for name, _ in columns)]
    lines = [row_line(head), row_line(["---"] * len(head))]
    return lines + [row_line([label, *(loop_value(s, field) for _, s in columns)]) for field, label in LOOP_ROWS]


def session_table(columns: list[Column], measures: list[Benchmark] = SESSION_MEASURES) -> list[str]:
    """bench's table without the 'Not measured' footer; deltas only between neighbouring columns."""
    return report_lines(columns, None, measures, [])


def finding_lines(found: list[Finding]) -> list[str]:
    if not found:
        return ["No rule fired for the latest week."]
    return [f"- **{f.key}** {f.evidence}. {f.suggestion}." for f in found]


NO_LOOP = "No loop stages recorded yet."
NO_SESSIONS = "No sessions in these weeks."


def loop_week_lines(weeks: list[Week]) -> list[str]:
    if not any(w.loop.runs or w.loop.stages for w in weeks):
        return [NO_LOOP]
    return loop_table([(w.name, w.loop) for w in weeks])


def session_week_lines(weeks: list[Week]) -> list[str]:
    """Only the weeks with sessions, so deltas compare neighbouring weeks that both have data."""
    columns = [Column(w.name, w.sessions, w.fix_share) for w in weeks if w.sessions]
    return session_table(columns) if columns else [NO_SESSIONS]


def repo_section(name: str, weeks: list[Week], loop_versions: list[tuple[str, LoopStats]], session_versions: list[Column], found: list[Finding]) -> list[str]:
    return [
        f"## {name}",
        "",
        "### Loop by week",
        "",
        *loop_week_lines(weeks),
        "",
        "### Loop by kit version",
        "",
        *(loop_table(loop_versions) if loop_versions else [NO_LOOP]),
        "",
        "### Sessions by week (loop sessions left out)",
        "",
        *session_week_lines(weeks),
        "",
        "### Sessions by kit version",
        "",
        *session_table(session_versions),
        "",
        "### Findings",
        "",
        *finding_lines(found),
        "",
    ]


def report_text(title: str, sections: list[list[str]], advice: list[str]) -> str:
    lines = [f"# kit insights: {title}", ""]
    for section in sections:
        lines += section
    if advice:
        lines += ["## Suggested changes", "", *advice, ""]
    return "\n".join(lines)
