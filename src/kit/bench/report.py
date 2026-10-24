"""The markdown table of benchmark measures per window, with deltas and optional control deltas."""

from __future__ import annotations

from dataclasses import dataclass

from kit.bench.benchmarks import Benchmark, fmt
from kit.bench.transcripts import Session

MIN_SESSIONS = 5
FIX_SHARE_ROW = ("Q4", "share of merges followed by a fix within 7 days", "falls")
NOT_ENOUGH = "not enough data"


@dataclass(frozen=True)
class Column:
    name: str
    sessions: list[Session]
    fix_share: float = float("nan")  # Q4: share of the window's merges followed by a fix


def row_line(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def delta(measure: Benchmark, earlier: Column, later: Column, min_sessions: int) -> str:
    if min(len(earlier.sessions), len(later.sessions)) < min_sessions:
        return NOT_ENOUGH
    return fmt(measure.measure(later.sessions) - measure.measure(earlier.sessions))


def fix_share_delta(earlier: Column, later: Column, min_sessions: int) -> str:
    if min(len(earlier.sessions), len(later.sessions)) < min_sessions:
        return NOT_ENOUGH
    return fmt(later.fix_share - earlier.fix_share)


def pairs(columns: list[Column]) -> list[tuple[int, int]]:
    return [(i, i + 1) for i in range(len(columns) - 1)]


def report_lines(
    columns: list[Column],
    control: list[Column] | None,
    measures: list[Benchmark],
    not_measured: list[str],
    min_sessions: int = MIN_SESSIONS,
) -> list[str]:
    delta_heads = []
    for a, b in pairs(columns):
        delta_heads.append(f"Δ {columns[a].name}→{columns[b].name}")
        if control is not None:
            delta_heads.append(f"control Δ {columns[a].name}→{columns[b].name}")
    head = ["measure", *(c.name for c in columns), *delta_heads, "target"]
    lines = [row_line(head), row_line(["---"] * len(head))]
    blanks = [""] * len(delta_heads)
    lines.append(row_line(["sessions", *(str(len(c.sessions)) for c in columns), *blanks, ""]))
    for m in measures:
        cells = [f"{m.key} {m.label}", *(fmt(m.measure(c.sessions)) for c in columns)]
        for a, b in pairs(columns):
            cells.append(delta(m, columns[a], columns[b], min_sessions))
            if control is not None:
                cells.append(delta(m, control[a], control[b], min_sessions))
        lines.append(row_line([*cells, m.target]))
    key, label, target = FIX_SHARE_ROW
    cells = [f"{key} {label}", *(fmt(c.fix_share) for c in columns)]
    for a, b in pairs(columns):
        cells.append(fix_share_delta(columns[a], columns[b], min_sessions))
        if control is not None:
            cells.append(fix_share_delta(control[a], control[b], min_sessions))
    lines.append(row_line([*cells, target]))
    if not_measured:
        lines += ["", "Not measured:", *(f"- {item}" for item in not_measured)]
    return lines
