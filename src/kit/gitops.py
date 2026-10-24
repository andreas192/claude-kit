"""The git and gh calls `apply` makes on the target repo, and the PR text."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from kit.gitrun import Runner
from kit.migrate import Migration
from kit.verify import Check, check_line

NONE = "- none"


def is_clean(repo: Path, run: Runner) -> bool:
    return run(["git", "status", "--porcelain"], repo).strip() == ""


def create_branch(repo: Path, name: str, run: Runner) -> None:
    run(["git", "checkout", "-b", name], repo)


def commit_all(repo: Path, message: str, run: Runner) -> str:
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", message], repo)
    return run(["git", "rev-parse", "HEAD"], repo).strip()


def commit_time(repo: Path, sha: str, run: Runner) -> str:
    epoch = int(run(["git", "show", "-s", "--format=%ct", sha], repo))
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_pr(repo: Path, title: str, body: str, run: Runner) -> str:
    """Push the branch (gh cannot open a PR for an unpushed one), open the PR and return its URL line."""
    run(["git", "push", "-u", "origin", "HEAD"], repo)
    out = run(["gh", "pr", "create", "--title", title, "--body", body], repo)
    return out.strip().splitlines()[-1]


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"### {title}", *(lines or [NONE]), ""]


def pr_body(
    version: str, m: Migration, removed_hooks: list[str], added: list[str], prose: list[str], checks: list[Check]
) -> str:
    removed = [*(f"- {name}" for name in m.remove), *(f"- hook entry: {command}" for command in removed_hooks)]
    lines = [
        f"## claude-kit {version}",
        "",
        *_section("Added", [f"- {name}" for name in added]),
        *_section("Removed (known kit content)", removed),
        *_section("Kept as local overrides", [f"- {name}" for name in m.overrides]),
        *_section("Edit by hand on this branch", [f"- {location}" for location in prose]),
        *_section("Checks", [f"- {check_line(check)}" for check in checks]),
    ]
    return "\n".join(lines)
