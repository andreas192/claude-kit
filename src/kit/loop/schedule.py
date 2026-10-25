"""The loop's launchd schedule: weekday gate, run hours, the plist, and other loop agents on a repo."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

WEEKDAYS = range(1, 6)  # launchd Weekday: 1 = Monday ... 5 = Friday
PLIST_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0">\n'
)


def may_start(now: datetime) -> bool:
    return now.weekday() < 5


def run_hours(interval_hours: int) -> list[int]:
    return list(range(0, 24, interval_hours))


def loop_label(repo_name: str) -> str:
    return f"com.kit.loop.{repo_name}"


def _string(value: str) -> str:
    return f"<string>{escape(value)}</string>"


def _key(name: str, value: str) -> str:
    return f"<key>{escape(name)}</key>{value}"


def _calendar_entries(hours: list[int], weekdays: Iterable[int]) -> str:
    return "".join(
        "<dict>"
        f"<key>Weekday</key><integer>{weekday}</integer>"
        f"<key>Hour</key><integer>{hour}</integer>"
        "<key>Minute</key><integer>0</integer>"
        "</dict>"
        for weekday in weekdays
        for hour in hours
    )


def _env_dict(env: dict[str, str]) -> str:
    return "<dict>" + "".join(_key(k, _string(v)) for k, v in env.items()) + "</dict>"


def plist_xml(
    label: str,
    program: list[str],
    env: dict[str, str],
    workdir: Path,
    log: Path,
    hours: list[int],
    weekdays: Iterable[int] = WEEKDAYS,
) -> str:
    args = "<array>" + "".join(_string(a) for a in program) + "</array>"
    body = "".join(
        [
            _key("Label", _string(label)),
            _key("ProgramArguments", args),
            _key("EnvironmentVariables", _env_dict(env)),
            _key("WorkingDirectory", _string(str(workdir))),
            _key("StandardOutPath", _string(str(log))),
            _key("StandardErrorPath", _string(str(log))),
            _key("RunAtLoad", "<false/>"),
            _key("StartCalendarInterval", f"<array>{_calendar_entries(hours, weekdays)}</array>"),
        ]
    )
    return f"{PLIST_HEADER}<dict>{body}</dict>\n</plist>\n"


def other_loop_agents(agents_dir: Path, repo: Path, own_label: str) -> list[Path]:
    own_name = f"{own_label}.plist"
    return sorted(
        path
        for path in agents_dir.glob("*.plist")
        if path.name != own_name and str(repo) in path.read_text()
    )
