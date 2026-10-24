"""Generated permissions for unattended loop sessions: the shipped base plus repo extras, pinned paths."""

from __future__ import annotations

import json
from pathlib import Path

BASE_SETTINGS_FILE = "base-settings.json"


def base_settings() -> dict:
    return json.loads(Path(__file__).with_name(BASE_SETTINGS_FILE).read_text())


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _absolute_rule(tool: str, path: Path) -> str:
    # Claude Code reads a single leading "/" as relative to the settings file;
    # an absolute filesystem path needs "//", so "/" + "/Users/..." gives "//Users/...".
    return f"{tool}(/{path}/**)"


def _forbidden_rules(repo: Path, forbidden: tuple[str, ...]) -> list[str]:
    rules: list[str] = []
    for path in forbidden:
        target = (repo / path).resolve()
        rules += [_absolute_rule("Edit", target), _absolute_rule("Write", target)]
    return rules


def loop_settings(
    base: dict,
    extra: dict,
    repo: Path,
    forbidden: tuple[str, ...],
    test_command: str,
    runtime: Path,
) -> dict:
    base_perms = base["permissions"]
    extra_perms = extra.get("permissions", {})
    allow = [
        *base_perms["allow"],
        *extra_perms.get("allow", []),
        f"Bash({test_command}*)",
        _absolute_rule("Write", runtime),
    ]
    deny = [
        *base_perms["deny"],
        *extra_perms.get("deny", []),
        *_forbidden_rules(repo, forbidden),
    ]
    return {"permissions": {"allow": _unique(allow), "deny": _unique(deny)}}
