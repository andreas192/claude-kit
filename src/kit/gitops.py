"""The git and gh calls `apply` makes on the target repo, and the PR text."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner
from kit.migrate import Migration
from kit.verify import Check, check_line

NONE = "- none"


def is_clean(repo: Path, run: Runner) -> bool:
    return run(["git", "status", "--porcelain"], repo).strip() == ""


def create_branch(repo: Path, name: str, run: Runner) -> None:
    run(["git", "checkout", "-b", name], repo)


def retry_hint(branch: str) -> str:
    """Undo a failed apply. Apply starts on a clean tree and stages nothing before its commit, so this removes only what it wrote."""
    return f"to retry: git checkout -- . && git clean -fd && git checkout - && git branch -D {branch}"


@contextmanager
def retry_hint_on_failure(branch: str) -> Iterator[None]:
    try:
        yield
    except KitError as error:
        raise KitError(f"{error}; {retry_hint(branch)}") from error


def commit_all(repo: Path, message: str, run: Runner) -> str:
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", message], repo)
    return run(["git", "rev-parse", "HEAD"], repo).strip()


def commit_time(repo: Path, sha: str, run: Runner) -> str:
    epoch = int(run(["git", "show", "-s", "--format=%ct", sha], repo))
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_pr(repo: Path, branch: str, title: str, body: str, run: Runner) -> str:
    """Push the branch (gh cannot open a PR for an unpushed one), open the PR and return its URL line."""
    run(["git", "push", "-u", "origin", "HEAD"], repo)
    by_hand = f"pushed {branch}; run gh pr create by hand"
    try:
        lines = run(["gh", "pr", "create", "--title", title, "--body", body], repo).strip().splitlines()
    except KitError as error:
        raise KitError(f"{error}; {by_hand}") from error
    if not lines:
        raise KitError(f"gh pr create printed no URL; {by_hand}")
    return lines[-1]


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
