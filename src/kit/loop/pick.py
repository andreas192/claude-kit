"""The deterministic pick: the first open roadmap item that nothing has taken and nothing blocks."""

from __future__ import annotations

from dataclasses import dataclass

from kit.loop.prs import LOOP_PREFIX, Pr, parse_park_body
from kit.roadmap import Item, Roadmap


@dataclass(frozen=True)
class Skip:
    item: Item
    reason: str


@dataclass(frozen=True)
class Pick:
    item: Item | None
    skipped: tuple[Skip, ...]


def _taken_reason(item: Item, branches: list[str], prs: list[Pr]) -> str:
    head = LOOP_PREFIX + item.key
    taking = sorted((p for p in prs if p.head == head), key=lambda p: p.created)
    if taking:
        return f"taken by {taking[-1].url}"
    return f"taken by branch {head}" if head in branches else ""


def _dependency_reason(item: Item, roadmap: Roadmap) -> str:
    for title in item.depends_on:
        dep = roadmap.by_title(title)
        if dep.status != "done":
            return f"depends on {dep.title} ({dep.status})"
    return ""


def _reason(item: Item, roadmap: Roadmap, branches: list[str], prs: list[Pr]) -> str:
    return _taken_reason(item, branches, prs) or _dependency_reason(item, roadmap)


def pick(roadmap: Roadmap, branches: list[str], prs: list[Pr]) -> Pick:
    chosen: Item | None = None
    skipped: list[Skip] = []
    for item in (i for i in roadmap.items if i.status == "open"):
        reason = _reason(item, roadmap, branches, prs)
        if reason:
            skipped.append(Skip(item, reason))
        elif chosen is None:
            chosen = item
    return Pick(chosen, tuple(skipped))


def _section(heading: str, bullets: list[str]) -> str:
    return "\n".join([f"## {heading}", "", *bullets]) if bullets else ""


def none_note(roadmap: Roadmap, prs: list[Pr]) -> str:
    def waiting(status: str) -> list[str]:
        return [f"- {i.title}: {i.blocked_by}" for i in roadmap.items if i.status == status]

    parked = [f"- {p.url}: {parse_park_body(p.body).reason or 'parked'}" for p in prs if p.is_draft and p.state == "OPEN"]
    sections = [
        _section("Waiting on the owner", waiting("owner")),
        _section("Blocked", waiting("blocked")),
        _section("Parked loop PRs", parked),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"
