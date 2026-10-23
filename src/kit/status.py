"""Which repos next to each other carry the kit, and at which version."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kit.kitfile import read_kitfile

NONE_FOUND = "no repos with .claude/kit.json found"


@dataclass(frozen=True)
class RepoStatus:
    name: str
    version: str
    overrides: tuple[str, ...]


def repo_status(repo: Path) -> RepoStatus | None:
    kit = read_kitfile(repo)
    if kit is None or not kit.applies:
        return None
    last = kit.applies[-1]
    return RepoStatus(repo.name, last.version, last.overrides)


def find_kit_repos(base: Path) -> list[RepoStatus]:
    children = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    return [status for status in map(repo_status, children) if status is not None]


def status_line(status: RepoStatus) -> str:
    line = f"{status.name}  {status.version}"
    return f"{line}  overrides: {', '.join(status.overrides)}" if status.overrides else line


def status_lines(repos: list[RepoStatus]) -> list[str]:
    return [status_line(r) for r in repos] or [NONE_FOUND]
