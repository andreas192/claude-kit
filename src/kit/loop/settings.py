"""Generated permissions for unattended loop sessions: the shipped base plus repo extras, pinned paths."""

from __future__ import annotations

import json
from pathlib import Path

BASE_SETTINGS_FILE = "base-settings.json"


def base_settings() -> dict:
    return json.loads(Path(__file__).with_name(BASE_SETTINGS_FILE).read_text())


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _forbidden_rules(repo: Path, forbidden: tuple[str, ...]) -> list[str]:
    rules: list[str] = []
    for path in forbidden:
        target = (repo / path).resolve()
        rules += [f"Edit({target}/**)", f"Write({target}/**)"]
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
        f"Write({runtime}/**)",
    ]
    deny = [
        *base_perms["deny"],
        *extra_perms.get("deny", []),
        *_forbidden_rules(repo, forbidden),
    ]
    return {"permissions": {"allow": _unique(allow), "deny": _unique(deny)}}
