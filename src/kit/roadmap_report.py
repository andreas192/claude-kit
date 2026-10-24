"""The text `kit roadmap` prints: counts, titles, reasons and questions only, never item bodies."""

from __future__ import annotations

from kit.loop.pick import Pick
from kit.loop.prs import Pr, parse_park_body
from kit.roadmap import STATUSES, Roadmap


def _counts(roadmap: Roadmap) -> str:
    counts = [sum(1 for item in roadmap.items if item.status == status) for status in STATUSES]
    return "Items: " + ", ".join(f"{n} {status}" for n, status in zip(counts, STATUSES, strict=True))


def _next_pick(result: Pick | None, gh_error: str) -> str:
    if result is None:
        return f"Next pick: unknown (gh: {gh_error or 'no pull request list'})"
    return f"Next pick: {result.item.title if result.item else 'none'}"


def _skipped(result: Pick | None) -> list[str]:
    if result is None or not result.skipped:
        return []
    return ["Skipped:", *(f"- {skip.item.title}: {skip.reason}" for skip in result.skipped)]


def _parked(pr: Pr) -> list[str]:
    note = parse_park_body(pr.body)
    return [f"- {pr.url}: {note.reason or 'parked'}", *(f"    - {question}" for question in note.questions)]


def _weekend(roadmap: Roadmap, prs: list[Pr] | None, gh_error: str) -> list[str]:
    lines = [f"- {item.title}: {item.blocked_by}" for item in roadmap.items if item.status == "owner"]
    if prs is None:
        lines.append(f"- parked PRs: unknown (gh: {gh_error or 'no pull request list'})")
    for pr in prs or []:
        if pr.is_draft and pr.state == "OPEN":
            lines += _parked(pr)
    return ["For you this weekend:", *lines] if lines else []


def format_report(roadmap: Roadmap, result: Pick | None, prs: list[Pr] | None, gh_error: str = "") -> str:
    lines = [_counts(roadmap), _next_pick(result, gh_error), *_skipped(result), *_weekend(roadmap, prs, gh_error)]
    return "\n".join(lines) + "\n"
