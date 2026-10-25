"""`stages.jsonl` in the loop's runtime directory: one line per stage session and one per run stop, numbers only."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kit.loop.stream import StageCost

LEDGER = "stages.jsonl"


@dataclass(frozen=True)
class StageEntry:
    time: str  # ISO with offset
    kit_version: str
    branch: str
    stage: str
    model: str
    outcome: str
    cost: StageCost | None


@dataclass(frozen=True)
class StopEntry:
    time: str
    kit_version: str
    reason: str


Entry = StageEntry | StopEntry


def entry_line(entry: Entry) -> str:
    kind = "stage" if isinstance(entry, StageEntry) else "stop"
    return json.dumps({"kind": kind, **asdict(entry)}, sort_keys=True)


def append_entry(runtime: Path, entry: Entry) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / LEDGER).open("a") as f:
        f.write(entry_line(entry) + "\n")


def parse_entry(line: str) -> Entry | None:
    """One ledger line; None for a blank, unparseable or unknown line, so one bad line never hides the rest."""
    try:
        raw = json.loads(line)
        kind = raw.pop("kind")
        if kind == "stop":
            return StopEntry(**raw)
        if kind == "stage":
            cost = raw.pop("cost")
            return StageEntry(**raw, cost=StageCost(**cost) if cost is not None else None)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return None


def read_ledger(runtime: Path) -> list[Entry]:
    path = runtime / LEDGER
    if not path.is_file():
        return []
    return [e for line in path.read_text().splitlines() if (e := parse_entry(line)) is not None]
