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


def parse_kitfile(text: str) -> KitFile:
    data = json.loads(text)
    applies = tuple(
        Apply(a["version"], a["commit"], a["applied_at"], tuple(a.get("overrides", ()))) for a in data["applies"]
    )
    return KitFile(data["test_command"], applies)


def read_kitfile(repo: Path) -> KitFile | None:
    path = repo / KITFILE
    if not path.is_file():
        return None
    try:
        return parse_kitfile(path.read_text())
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        reason = f"missing {exc}" if isinstance(exc, KeyError) else str(exc)
        raise KitError(f"{path}: invalid kit.json: {reason}") from exc


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
