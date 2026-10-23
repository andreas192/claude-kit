"""Merge history from git: when a kit version landed and whether a merge was followed by a fix."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner

FIX_WINDOW_DAYS = 7
FIX = re.compile(r"\b(fix|revert)", re.I)
ORIGIN = "origin/"
FALLBACK_BRANCH = "main"


@dataclass(frozen=True)
class Merge:
    sha: str
    time: str
    subject: str
    files: frozenset[str]


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def default_branch(repo: Path, run: Runner) -> str:
    try:
        ref = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], repo).strip()
    except KitError:
        return FALLBACK_BRANCH
    return ref.removeprefix(ORIGIN) or FALLBACK_BRANCH


def parse_merge(block: str) -> Merge:
    header, _, names = block.partition("\n")
    sha, time, subject = header.split("\t", 2)
    return Merge(sha, time, subject, frozenset(n for n in names.splitlines() if n))


def merges(repo: Path, branch: str, run: Runner) -> list[Merge]:
    out = run(
        ["git", "log", "--first-parent", "-m", "--reverse", "--name-only", "--format=%x00%H%x09%cI%x09%s", branch],
        repo,
    )
    return [parse_merge(block) for block in out.split("\x00") if block.strip()]


def followed_by_fix(ms: list[Merge], days: int = FIX_WINDOW_DAYS) -> list[bool]:
    window = timedelta(days=days)
    times = [parse_time(m.time) for m in ms]
    return [
        any(
            FIX.search(later.subject) and m.files & later.files
            for later, at in zip(ms[i + 1 :], times[i + 1 :])
            if timedelta(0) <= at - times[i] <= window
        )
        for i, m in enumerate(ms)
    ]


def merged_at(repo: Path, version: str, branch: str, run: Runner) -> str | None:
    out = run(
        ["git", "log", "--first-parent", "--reverse", "--format=%cI", f'-S"version": "{version}"', branch, "--", ".claude/kit.json"],
        repo,
    )
    lines = out.split()
    return lines[0] if lines else None


def history(repo: Path, run: Runner) -> list[Merge]:
    """The default branch's merges with an empty list for a directory that is not a git repo with commits."""
    try:
        return merges(repo, default_branch(repo, run), run)
    except KitError:
        return []
