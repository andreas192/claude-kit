"""Which snapshot the loop runs from: hand over to the newest applied one when it is newer than this process."""

from __future__ import annotations

from pathlib import Path

from kit.kitfile import parse_kitfile
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
