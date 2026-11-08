"""The command agents run kit with (`kit` is not on PATH), and the rewrite of bare `kit <cmd>` in a repo's docs."""

from __future__ import annotations

import re
from pathlib import Path

from kit.kitfile import read_kitfile

DEFAULT_COMMAND = "uv run --project ~/Projects/Personal/claude-kit kit"
SUBCOMMANDS = ("apply", "bench", "status", "roadmap", "loop", "request", "insights")
_SUB = "|".join(SUBCOMMANDS)
SPAN = re.compile(rf"`kit (?=(?:{_SUB})\b)")
BLOCK_LINE = re.compile(rf"^(\s*)kit (?=(?:{_SUB})\b)")
FENCE = re.compile(r"^\s*(```|~~~)")


def kit_command(kit_repo: Path) -> str:
    return f"uv run --project {kit_repo} kit"


def command_for(repo: Path) -> str:
    """The command `kit apply` recorded in the repo's kit.json, else the default checkout."""
    kit = read_kitfile(repo)
    return kit.kit_command if kit and kit.kit_command else DEFAULT_COMMAND


def rewrite_line(line: str, command: str, in_block: bool) -> str:
    if in_block:
        return BLOCK_LINE.sub(lambda m: f"{m.group(1)}{command} ", line)
    return SPAN.sub(f"`{command} ", line)


def rewrite_text(text: str, command: str) -> tuple[str, list[int]]:
    """Code spans and code-block lines that start with `kit <subcommand>` get the full command; returns the changed line numbers."""
    out: list[str] = []
    changed: list[int] = []
    in_block = False
    for number, line in enumerate(text.splitlines(keepends=True), start=1):
        if FENCE.match(line):
            in_block = not in_block
            out.append(line)
            continue
        new = rewrite_line(line, command, in_block)
        if new != line:
            changed.append(number)
        out.append(new)
    return "".join(out), changed


def doc_files(repo: Path) -> list[Path]:
    """CLAUDE.md and top-level docs/*.md; docs/superpowers holds specs and plans, which are history."""
    claude = [repo / "CLAUDE.md"] if (repo / "CLAUDE.md").is_file() else []
    return [*claude, *sorted((repo / "docs").glob("*.md"))]


def rewrite_docs(repo: Path, command: str) -> list[str]:
    """Rewrite each doc in place; returns `path:line` for every changed line."""
    hits: list[str] = []
    for path in doc_files(repo):
        text, changed = rewrite_text(path.read_text(), command)
        if changed:
            path.write_text(text)
            name = path.relative_to(repo).as_posix()
            hits.extend(f"{name}:{number}" for number in changed)
    return hits


def with_command(files: dict[str, str], command: str) -> dict[str, str]:
    """Starter files name the default checkout; fill in the one this apply runs from."""
    return {name: text.replace(DEFAULT_COMMAND, command) for name, text in files.items()}
