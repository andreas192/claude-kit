"""Version windows: which kit version was active when a session started."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from kit.bench.gitlog import Merge, parse_time
from kit.bench.transcripts import Session
from kit.errors import KitError

PRE_KIT = "pre-kit"


@dataclass(frozen=True)
class Window:
    name: str
    start: str  # ISO UTC; "" = open
    end: str  # ISO UTC; "" = open


def make_windows(times: list[tuple[str, str]]) -> list[Window]:
    """`(version, effective time)` in apply order -> `pre-kit`, then one window per version."""
    names = [PRE_KIT] + [version for version, _ in times]
    starts = [""] + [time for _, time in times]
    ends = starts[1:] + [""]
    return [Window(n, s, e) for n, s, e in zip(names, starts, ends)]


def parse_utc(text: str) -> datetime | None:
    """A zone-aware time, `Z` normalized; no zone means UTC; empty or unparseable -> None."""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def contains(window: Window, moment: datetime) -> bool:
    start, end = parse_utc(window.start), parse_utc(window.end)
    return (start is None or start <= moment) and (end is None or moment < end)


def assign(sessions: list[Session], windows: list[Window]) -> dict[str, list[Session]]:
    """Each session lands in the window holding its first record; sessions with no start are dropped."""
    grouped: dict[str, list[Session]] = {w.name: [] for w in windows}
    for session in sessions:
        moment = parse_utc(session.main.start)
        if moment is None:
            continue
        for window in windows:
            if contains(window, moment):
                grouped[window.name].append(session)
                break
    return grouped


def drop_before(sessions: list[Session], since: str) -> list[Session]:
    """Sessions whose first record is at or after `since` (ISO UTC); no `since` keeps all."""
    if not since:
        return sessions
    cutoff = parse_utc(since)
    if cutoff is None:
        raise KitError(f"--since is not an ISO time: {since}")
    return [s for s in sessions if (start := parse_utc(s.main.start)) is not None and start >= cutoff]


def fix_share(window: Window, ms: list[Merge], flags: list[bool]) -> float:
    """Q4: of the merges whose time falls in the window, the share followed by a fix; NaN when none."""
    inside = [fixed for m, fixed in zip(ms, flags) if contains(window, parse_time(m.time))]
    return sum(inside) / len(inside) if inside else float("nan")
