"""Loop pull requests: reading them from `gh` and the park note carried in a draft PR body."""

from __future__ import annotations

import json
from dataclasses import dataclass

PR_FIELDS = "number,headRefName,state,createdAt,url,title,isDraft,body"
LOOP_PREFIX = "loop/"
ATTRIBUTION = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
PARKED = "Parked: "
SPEC = "Spec: "
PLAN = "Plan: "
QUESTIONS_HEADING = "## Questions for the owner"


@dataclass(frozen=True)
class Pr:
    number: int
    head: str
    state: str
    created: str
    url: str
    title: str = ""
    is_draft: bool = False
    body: str = ""


@dataclass(frozen=True)
class ParkNote:
    reason: str
    questions: tuple[str, ...]


def loop_prs(gh_json: str) -> list[Pr]:
    prs = [
        Pr(p["number"], p["headRefName"], p["state"], p["createdAt"], p["url"], p.get("title", ""), p.get("isDraft", False), p.get("body", ""))
        for p in json.loads(gh_json)
        if p["headRefName"].startswith(LOOP_PREFIX)
    ]
    return sorted(prs, key=lambda p: p.created)


def park_body(reason: str, spec: str, plan: str, questions: list[str]) -> str:
    parts = [PARKED + reason]
    refs = [label + path for label, path in ((SPEC, spec), (PLAN, plan)) if path]
    if refs:
        parts.append("\n".join(refs))
    if questions:
        parts.append("\n".join([QUESTIONS_HEADING, "", *(f"- {q}" for q in questions)]))
    parts.append(ATTRIBUTION)
    return "\n\n".join(parts) + "\n"


def parse_park_body(body: str) -> ParkNote:
    lines = [line.strip() for line in body.splitlines()]
    reason = next((line[len(PARKED) :] for line in lines if line.startswith(PARKED)), "")
    after = lines[lines.index(QUESTIONS_HEADING) + 1 :] if QUESTIONS_HEADING in lines else []
    return ParkNote(reason, tuple(line[2:] for line in after if line.startswith("- ")))
