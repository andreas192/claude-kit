"""Which snapshot the loop runs from: hand over to the newest applied one when it is newer than this process."""

from __future__ import annotations

from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner
from kit.kitfile import KITFILE, parse_kitfile
from kit.snapshot import parse_version


def snapshot_src(kit_home: Path, version: str) -> Path:
    return kit_home / version / "src"


def latest_applied(kit_json_text: str) -> str | None:
    applies = parse_kitfile(kit_json_text).applies
    return applies[-1].version if applies else None


def handover_target(latest: str | None, running: str, kit_home: Path) -> Path | None:
    """The snapshot src to re-exec into, or None when latest is absent, not newer, or not installed."""
    if latest is None or parse_version(latest) <= parse_version(running):
        return None
    src = snapshot_src(kit_home, latest)
    return src if (src / "kit" / "cli.py").is_file() else None


def origin_latest(repo: Path, base_branch: str, runner: Runner) -> str:
    """The latest applied kit version in .claude/kit.json on origin/<base_branch>, after a fetch."""
    ref = f"origin/{base_branch}:{KITFILE.as_posix()}"
    runner(["git", "fetch", "origin"], repo)
    try:
        text = runner(["git", "show", ref], repo)
    except KitError as error:
        raise KitError(f"no {KITFILE.as_posix()} on origin/{base_branch}") from error
    try:
        latest = latest_applied(text)
    except (ValueError, KeyError, TypeError, AttributeError, KitError) as error:
        raise KitError(f"{ref} is not valid: {error}") from error
    if latest is None:
        raise KitError(f"{ref} has no applied version")
    return latest
