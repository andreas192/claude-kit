"""The loop's alert records in the runtime dir: a failing probe (probe-failure.txt) and a run stopped on an env failure (env-failure.txt). Each is one file from its first failure until a later run clears it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

PROBE_FAILURE_FILE = "probe-failure.txt"
ENV_FAILURE_FILE = "env-failure.txt"


def _read(runtime: Path, name: str) -> tuple[str, str] | None:
    path = runtime / name
    if not path.is_file():
        return None
    text = path.read_text().strip()
    if not text:
        return None
    since, _, why = text.partition(" ")
    return since, why


def _record(runtime: Path, name: str, when: datetime, why: str) -> None:
    """Keep the time of the first failure; the reason is the latest one."""
    known = _read(runtime, name)
    since = known[0] if known else when.isoformat(timespec="seconds")
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / name).write_text(f"{since} {' '.join(why.split())}\n")


def _clear(runtime: Path, name: str) -> None:
    (runtime / name).unlink(missing_ok=True)


def record_probe_failure(runtime: Path, when: datetime, why: str) -> None:
    _record(runtime, PROBE_FAILURE_FILE, when, why)


def clear_probe_failure(runtime: Path) -> None:
    _clear(runtime, PROBE_FAILURE_FILE)


def probe_failure_line(runtime: Path) -> str:
    known = _read(runtime, PROBE_FAILURE_FILE)
    return f"loop probe failing since {known[0]}: {known[1]}" if known else ""


def record_env_failure(runtime: Path, when: datetime, why: str) -> None:
    _record(runtime, ENV_FAILURE_FILE, when, why)


def clear_env_failure(runtime: Path) -> None:
    _clear(runtime, ENV_FAILURE_FILE)


def env_failure_line(runtime: Path) -> str:
    known = _read(runtime, ENV_FAILURE_FILE)
    return f"loop stopped since {known[0]}: {known[1]}" if known else ""


def alert_lines(runtime: Path) -> list[str]:
    """The probe line, then the env-stop line, each only when its record exists."""
    return [line for line in (probe_failure_line(runtime), env_failure_line(runtime)) if line]
