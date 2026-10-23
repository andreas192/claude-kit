"""`.claude/kit.json`: the kit versions applied to a repo, in order."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kit.errors import KitError

KITFILE = Path(".claude") / "kit.json"


@dataclass(frozen=True)
class Apply:
    version: str
    commit: str
    applied_at: str
    overrides: tuple[str, ...] = ()


@dataclass(frozen=True)
class KitFile:
    test_command: str
    applies: tuple[Apply, ...]


def read_kitfile(repo: Path) -> KitFile | None:
    path = repo / KITFILE
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    applies = tuple(
        Apply(a["version"], a["commit"], a["applied_at"], tuple(a.get("overrides", ()))) for a in data["applies"]
    )
    return KitFile(data["test_command"], applies)


def with_apply(kit: KitFile, apply: Apply) -> KitFile:
    if kit.applies and kit.applies[-1].version == apply.version:
        raise KitError(f"already on {apply.version}")
    return KitFile(kit.test_command, (*kit.applies, apply))


def write_kitfile(repo: Path, kit: KitFile) -> None:
    """Indent-2 JSON: `git log -S'"version": "<v>"'` finds the apply commit from this exact spelling."""
    path = repo / KITFILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "test_command": kit.test_command,
        "applies": [{**asdict(a), "overrides": list(a.overrides)} for a in kit.applies],
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
