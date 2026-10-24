"""`.claude/kit.json`: the kit versions applied to a repo, in order, and the optional loop settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kit.errors import KitError

KITFILE = Path(".claude") / "kit.json"
DEFAULT_INTERVAL_HOURS = 5
LOOP_KEYS = frozenset({"base_branch", "forbidden_paths", "read_first", "pr_checklist", "interval_hours"})


@dataclass(frozen=True)
class Apply:
    version: str
    commit: str
    applied_at: str
    overrides: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoopConfig:
    base_branch: str
    forbidden_paths: tuple[str, ...] = ()
    read_first: tuple[str, ...] = ()
    pr_checklist: tuple[str, ...] = ()
    interval_hours: int = DEFAULT_INTERVAL_HOURS


@dataclass(frozen=True)
class KitFile:
    test_command: str
    applies: tuple[Apply, ...]
    loop: LoopConfig | None = None


def parse_kitfile(text: str) -> KitFile:
    data = json.loads(text)
    applies = tuple(
        Apply(a["version"], a["commit"], a["applied_at"], tuple(a.get("overrides", ()))) for a in data["applies"]
    )
    return KitFile(data["test_command"], applies, optional_loop(data))


def optional_loop(data: dict[str, Any]) -> LoopConfig | None:
    if "loop" not in data:
        return None
    if not isinstance(data["loop"], dict):
        raise KitError("loop must be an object")
    return parse_loop(data["loop"])


def parse_loop(raw: dict[str, Any]) -> LoopConfig:
    unknown = sorted(set(raw) - LOOP_KEYS)
    if unknown:
        raise KitError(f"loop has unknown key {unknown[0]!r}")
    base = raw["base_branch"]
    if not isinstance(base, str) or not base:
        raise KitError("loop.base_branch must be a non-empty string")
    return LoopConfig(
        base,
        string_tuple(raw, "forbidden_paths"),
        string_tuple(raw, "read_first"),
        string_tuple(raw, "pr_checklist"),
        interval_hours(raw.get("interval_hours", DEFAULT_INTERVAL_HOURS)),
    )


def string_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise KitError(f"loop.{key} must be a list of strings")
    return tuple(value)


def interval_hours(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 24:
        raise KitError("loop.interval_hours must be an integer from 1 to 24")
    return value


def read_kitfile(repo: Path) -> KitFile | None:
    path = repo / KITFILE
    if not path.is_file():
        return None
    try:
        return parse_kitfile(path.read_text())
    except KitError as exc:
        raise KitError(f"{path}: invalid kit.json: {exc}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        reason = f"missing {exc}" if isinstance(exc, KeyError) else str(exc)
        raise KitError(f"{path}: invalid kit.json: {reason}") from exc


def with_apply(kit: KitFile, apply: Apply) -> KitFile:
    if kit.applies and kit.applies[-1].version == apply.version:
        raise KitError(f"already on {apply.version}")
    return KitFile(kit.test_command, (*kit.applies, apply), kit.loop)


def loop_json(loop: LoopConfig) -> dict[str, Any]:
    return {key: list(value) if isinstance(value, tuple) else value for key, value in asdict(loop).items()}


def write_kitfile(repo: Path, kit: KitFile) -> None:
    """Indent-2 JSON: `git log -S'"version": "<v>"'` finds the apply commit from this exact spelling."""
    path = repo / KITFILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "test_command": kit.test_command,
        "applies": [{**asdict(a), "overrides": list(a.overrides)} for a in kit.applies],
    }
    if kit.loop is not None:
        data["loop"] = loop_json(kit.loop)
    path.write_text(json.dumps(data, indent=2) + "\n")
