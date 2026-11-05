"""The record of a failing probe: one file in the runtime dir, from the first failure until a probe works."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

PROBE_FAILURE_FILE = "probe-failure.txt"


def _read(runtime: Path) -> tuple[str, str] | None:
    path = runtime / PROBE_FAILURE_FILE
    if not path.is_file():
        return None
    since, _, why = path.read_text().strip().partition(" ")
    return since, why


def record_probe_failure(runtime: Path, when: datetime, why: str) -> None:
    """Keep the time of the first failure; the reason is the latest one."""
    known = _read(runtime)
    since = known[0] if known else when.isoformat(timespec="seconds")
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / PROBE_FAILURE_FILE).write_text(f"{since} {' '.join(why.split())}\n")


def clear_probe_failure(runtime: Path) -> None:
    (runtime / PROBE_FAILURE_FILE).unlink(missing_ok=True)


def probe_failure_line(runtime: Path) -> str:
    known = _read(runtime)
    return f"loop probe failing since {known[0]}: {known[1]}" if known else ""
