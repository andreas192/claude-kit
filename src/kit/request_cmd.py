"""File a cross-repo request: one roadmap commit on `request/<key>` from a temporary worktree of the target, pushed as a PR.

The target's own checkout is never touched: the only commands run there are `git fetch origin`, read-only queries,
`git worktree add/remove` and `git branch -D request/<key>` for the branch this module created.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner
from kit.kitfile import KITFILE, KitFile, read_kitfile
from kit.loop.handover import origin_latest
from kit.loop.requests import RequestRecord
from kit.request import (
    Request,
    commit_message,
    existing_item,
    filed_item,
    parse_request,
    pr_body,
    pr_title,
    require_version,
    target_by_name,
    with_request,
)
from kit.roadmap import ROADMAP_PATH, parse_roadmap

REQUESTS_DIR = "requests"
BRANCH_PREFIX = "request/"
UNKNOWN_TARGET = "unknown"


@dataclass(frozen=True)
class Filed:
    target: str
    title: str
    url: str


def _first_line(error: KitError) -> str:
    lines = str(error).splitlines()
    return lines[0] if lines else ""


def request_branch(key: str) -> str:
    return f"{BRANCH_PREFIX}{key}"


def require_target_kit(target: Path) -> KitFile:
    kit = read_kitfile(target)
    if kit is None:
        raise KitError(f"{target.name} has no {KITFILE.as_posix()}")
    return kit


def origin_head(target: Path, run: Runner) -> str:
    try:
        ref = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], target).strip()
    except KitError as error:
        raise KitError(f"{target.name} has no origin/HEAD; run git remote set-head origin -a there") from error
    return ref.removeprefix("origin/")


def target_base(target: Path, run: Runner) -> str:
    """The branch requests go against: the target's loop.base_branch, else origin/HEAD, after a fetch."""
    run(["git", "fetch", "origin"], target)
    kit = read_kitfile(target)
    if kit is not None and kit.loop is not None:
        return kit.loop.base_branch
    return origin_head(target, run)


def base_roadmap_text(target: Path, base: str, run: Runner) -> str:
    """The roadmap on origin/<base>, checked to parse; one-line KitError when missing or invalid."""
    try:
        text = run(["git", "show", f"origin/{base}:{ROADMAP_PATH.as_posix()}"], target)
        parse_roadmap(text)
    except KitError as error:
        raise KitError(f"{target.name} has no valid {ROADMAP_PATH.as_posix()} on origin/{base}: {_first_line(error)}") from error
    return text


def require_new_title(target: Path, roadmap_text: str, key: str) -> None:
    item = existing_item(parse_roadmap(roadmap_text), key)
    if item is not None:
        raise KitError(f"{target.name} already has {item.title!r} (line {item.line})")


def open_request_urls(target: Path, key: str, run: Runner) -> list[str]:
    out = run(["gh", "pr", "list", "--head", request_branch(key), "--state", "open", "--json", "url"], target)
    try:
        return [pr["url"] for pr in json.loads(out)]
    except (ValueError, KeyError, TypeError) as error:
        raise KitError(f"gh pr list in {target.name} printed unreadable output") from error


def require_no_open_pr(target: Path, key: str, run: Runner) -> None:
    urls = open_request_urls(target, key, run)
    if urls:
        raise KitError(f"open request PR already exists: {urls[0]}")


def require_no_remote_branch(target: Path, key: str, run: Runner) -> None:
    """Refuse a request/<key> already on origin (failed PR create, or a closed PR whose branch was kept); never force-push."""
    branch = request_branch(key)
    if run(["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"], target).strip():
        raise KitError(f"origin of {target.name} already has branch {branch} with no open PR; delete it there first")


def new_roadmap_text(target: Path, base_text: str, item_text: str) -> str:
    try:
        return with_request(base_text, item_text)
    except KitError as error:
        raise KitError(f"the request does not fit {target.name}'s roadmap: {_first_line(error)}") from error


def worktree_path(target: Path, key: str, kit_home: Path) -> Path:
    return kit_home / REQUESTS_DIR / f"{target.name}-{key}"


def require_fresh(target: Path, path: Path, branch: str, run: Runner) -> None:
    """Refuse a branch or path left from elsewhere, so cleanup only ever removes what this run created."""
    if run(["git", "branch", "--list", branch], target).strip():
        raise KitError(f"{target.name} already has a local branch {branch}; delete it there first")
    if path.exists():
        raise KitError(f"{path} already exists; remove it first")


def remove_worktree(target: Path, path: Path, branch: str, run: Runner) -> None:
    """Best effort: try both steps; a failure here must not hide the error that got us here."""
    for cmd in (["git", "worktree", "remove", "--force", str(path)], ["git", "branch", "-D", branch]):
        try:
            run(cmd, target)
        except KitError:
            pass


@contextmanager
def request_worktree(target: Path, base: str, key: str, kit_home: Path, run: Runner) -> Iterator[Path]:
    """A worktree of the target on a new branch request/<key> from origin/<base>; removed with its branch afterwards."""
    path, branch = worktree_path(target, key, kit_home), request_branch(key)
    require_fresh(target, path, branch, run)
    try:
        run(["git", "worktree", "add", "-b", branch, str(path), f"origin/{base}"], target)
        yield path
    finally:
        remove_worktree(target, path, branch, run)


def run_labelled(run: Runner, cmd: list[str], cwd: Path, label: str) -> str:
    """Run a command whose arguments hold multi-line text; its error names only `label`, so it stays one line."""
    try:
        return run(cmd, cwd)
    except KitError as error:
        raise KitError(f"{label} failed: {str(error).rsplit(' failed: ', 1)[-1].strip()}") from error


def pr_url(out: str) -> str:
    lines = out.strip().splitlines()
    if not lines:
        raise KitError("gh pr create printed no PR URL")
    return lines[-1].strip()


def commit_and_open_pr(worktree: Path, base: str, key: str, text: str, message: str, title: str, body: str, run: Runner) -> str:
    (worktree / ROADMAP_PATH).write_text(text)
    run(["git", "add", ROADMAP_PATH.as_posix()], worktree)
    run_labelled(run, ["git", "commit", "-m", message], worktree, "git commit")
    branch = request_branch(key)
    run(["git", "push", "-u", "origin", branch], worktree)
    create = ["gh", "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body]
    return pr_url(run_labelled(run, create, worktree, f"gh pr create --head {branch}"))


def file_request(requester: Path, target: Path, request: Request, kit_home: Path, run: Runner, loop_branch: str = "") -> Filed:
    """Check the target, then commit the filed item on request/<key> in a temporary worktree, push it and open a PR."""
    require_target_kit(target)
    base = target_base(target, run)
    require_version(origin_latest(target, base, run), target.name)
    base_text = base_roadmap_text(target, base, run)
    require_new_title(target, base_text, request.key)
    require_no_open_pr(target, request.key, run)
    require_no_remote_branch(target, request.key, run)
    item_text = filed_item(request, requester.name)
    text = new_roadmap_text(target, base_text, item_text)
    message = commit_message(requester.name, request.title)
    title, body = pr_title(requester.name, request.title), pr_body(item_text, requester.name, loop_branch)
    with request_worktree(target, base, request.key, kit_home, run) as worktree:
        url = commit_and_open_pr(worktree, base, request.key, text, message, title, body, run)
    return Filed(target.name, request.title, url)


def read_request_file(path: Path) -> Request:
    try:
        text = path.read_text()
    except OSError as error:
        raise KitError(f"cannot read request file {path}: {error.strerror}") from error
    return parse_request(text)


def file_request_file(
    requester: Path, targets: tuple[str, ...], kit_home: Path, run: Runner, path: Path, loop_branch: str
) -> RequestRecord:
    """File the request in `path`; any KitError becomes an error record (titled by the file when it does not parse)."""
    request: Request | None = None
    try:
        request = read_request_file(path)
        target = target_by_name(requester, targets, request.target)
        filed = file_request(requester, target, request, kit_home, run, loop_branch)
    except KitError as error:
        name, title = (request.target or UNKNOWN_TARGET, request.title) if request else (UNKNOWN_TARGET, path.name)
        return RequestRecord(name, title, error=_first_line(error) or type(error).__name__)
    return RequestRecord(filed.target, filed.title, url=filed.url)
