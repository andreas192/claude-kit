"""The per-branch status file `.loop/status.json` and the order of the stages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kit.loop.prs import Pr
from kit.roadmap import item_key

STAGES = ("spec", "plan", "build", "pr")
CALLS_HEADING = "## Calls made for the owner"


@dataclass
class Status:
    key: str
    row: str
    stage: str
    spec: str
    plan: str


def unfinished(branches: list[str], prs: list[Pr], live: set[str] = frozenset()) -> str | None:
    heads = {p.head for p in prs}
    return next((b for b in sorted(branches) if b not in heads or b in live), None)


def is_live(raw: str | None) -> bool:
    """A branch tip whose status file is not parked is still being worked, even if a PR exists for it."""
    return raw is not None and json.loads(raw).get("stage") != "parked"


def read_status(path: Path) -> Status | None:
    if not path.exists():
        return None
    return Status(**json.loads(path.read_text()))


def write_status(path: Path, status: Status) -> None:
    path.write_text(json.dumps(asdict(status), sort_keys=True) + "\n")


def resume_stage(status: Status | None) -> str:
    return status.stage if status else "pr"


def next_stage(stage: str, outcome: str) -> str:
    if outcome == "park":
        return "parked"
    if outcome == "more":
        return "build"
    i = STAGES.index(stage) + 1
    return STAGES[i] if i < len(STAGES) else "done"


def new_status(title: str, today: str) -> Status:
    key = item_key(title)
    spec = f"docs/superpowers/specs/{today}-{key}-design.md"
    plan = f"docs/superpowers/plans/{today}-{key}.md"
    return Status(key, title, "spec", spec, plan)


def has_calls_section(spec_text: str) -> bool:
    lines = spec_text.splitlines()
    if CALLS_HEADING not in lines:
        return False
    body = []
    for line in lines[lines.index(CALLS_HEADING) + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    bullets = [line for line in body if line.startswith("- ")]
    return bool(bullets) and all("Rejected:" in b for b in bullets)
