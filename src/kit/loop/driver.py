"""Feature loop driver: one claude session per stage, the pick made in code from docs/roadmap.md."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import subprocess
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

from kit.kitfile import LoopConfig
from kit.loop.pick import Pick, none_note
from kit.loop.pick import pick as choose
from kit.loop.prs import PR_FIELDS, Pr, loop_prs, park_body
from kit.loop.schedule import may_start
from kit.loop.state import (
    Status,
    has_calls_section,
    is_live,
    new_status,
    next_stage,
    owner_questions,
    read_status,
    resume_stage,
    unfinished,
    write_status,
)
from kit.loop.stream import StageResult, Usage, over_limit, parse_stream
from kit.roadmap import ROADMAP_PATH, Roadmap, RoadmapError, parse_roadmap

PROMPTS = Path(__file__).with_name("prompts")
CO_AUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
MAX_ERRORS = 2
_ROADMAP_FILE = ROADMAP_PATH.as_posix()
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_BLANK_FIELDS = dict.fromkeys(("row", "key", "branch", "spec", "plan"), "")


@dataclass
class Env:
    claude: Callable[[str, str], list[str]]
    sh: Callable[[list[str]], str]
    notify: Callable[[str], None]
    log: Callable[[str], None]
    worktree: Path
    runtime: Path
    today: str
    now: Callable[[], datetime]
    config: LoopConfig
    test_command: str
    repo_name: str
    weekend_ok: bool = False


def _ticked(paths: tuple[str, ...]) -> str:
    quoted = [f"`{p}`" for p in paths]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} or {quoted[-1]}"


def _rules(config: LoopConfig) -> str:
    never_write = f"never write {_ticked(config.forbidden_paths)}; " if config.forbidden_paths else ""
    return f"{never_write}never merge or force-push; every commit message ends with the line `{CO_AUTHOR}`"


def _read_first(config: LoopConfig) -> str:
    return f"\nRead these first: {_ticked(config.read_first)}.\n" if config.read_first else ""


def _checklist(config: LoopConfig) -> str:
    return "".join(f"{n}. {step}\n" for n, step in enumerate(config.pr_checklist, start=2))


def _config_fields(env: Env) -> dict[str, str]:
    steps = len(env.config.pr_checklist)
    return {
        "test_command": env.test_command,
        "base_branch": env.config.base_branch,
        "rules": _rules(env.config),
        "read_first": _read_first(env.config),
        "pr_checklist": _checklist(env.config),
        "n_create": str(steps + 2),
        "n_roadmap": str(steps + 3),
        "pr_body": str(env.runtime / "pr-body.md"),
    }


def render(stage: str, env: Env, **fields: str) -> str:
    values = {**_BLANK_FIELDS, **_config_fields(env), **fields}
    text = (PROMPTS / f"{stage}.md").read_text()
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def acquire_lock(path: Path) -> IO | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _state_path(env: Env) -> Path:
    return env.runtime / "state.json"


def _read_state(env: Env) -> dict:
    path = _state_path(env)
    return json.loads(path.read_text()) if path.exists() else {}


def _write_runtime(env: Env, name: str, text: str) -> Path:
    env.runtime.mkdir(parents=True, exist_ok=True)
    path = env.runtime / name
    path.write_text(text)
    return path


def _write_state(env: Env, state: dict) -> None:
    _write_runtime(env, "state.json", json.dumps(state, sort_keys=True) + "\n")


def _snapshot(env: Env) -> tuple[list[Pr], list[str]]:
    env.sh(["git", "fetch", "origin", "--prune"])
    prs = loop_prs(env.sh(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json", PR_FIELDS]))
    heads = env.sh(["git", "ls-remote", "--heads", "origin", "loop/*"])
    return prs, [ln.split("refs/heads/", 1)[1] for ln in heads.splitlines() if "refs/heads/" in ln]


def _tip_status(env: Env, branch: str) -> str | None:
    try:
        return env.sh(["git", "show", f"origin/{branch}:.loop/status.json"])
    except subprocess.CalledProcessError:
        return None


def _live(env: Env, branches: list[str], prs: list[Pr]) -> set[str]:
    heads = {p.head for p in prs}
    return {b for b in branches if b in heads and is_live(_tip_status(env, b))}


def _usage_text(usage: Usage | None) -> str:
    return f"five_hour={usage.five_hour:.2f} seven_day={usage.seven_day:.2f}" if usage else "usage unknown"


def _log_result(env: Env, what: str, r: StageResult) -> None:
    env.log(f"{what} {r.outcome} {r.detail} {_usage_text(r.usage)}".replace("  ", " "))


def _status_path(env: Env) -> Path:
    return env.worktree / ".loop" / "status.json"


def _commit(env: Env, branch: str, message: str, paths: list[str]) -> None:
    if paths:
        env.sh(["git", "add", *paths])
    env.sh(["git", "commit", "-m", f"{message}\n\n{CO_AUTHOR}"])
    env.sh(["git", "push", "-u", "origin", branch])


def _save_stage(env: Env, branch: str, status: Status, stage: str) -> None:
    status.stage = stage
    _status_path(env).parent.mkdir(parents=True, exist_ok=True)
    write_status(_status_path(env), status)
    _commit(env, branch, f"chore(loop): {status.key} stage {stage}", [".loop/status.json"])


def _open_prs(env: Env, branch: str) -> list[dict]:
    return json.loads(env.sh(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number,isDraft"]))


def _open_draft(env: Env, branch: str, status: Status | None, reason: str) -> None:
    key = status.key if status else branch.removeprefix("loop/")
    spec, plan = (status.spec, status.plan) if status else ("", "")
    body = park_body(reason, spec, plan, owner_questions(_read(env.worktree / spec)) if spec else [])
    title = f"loop (parked): {status.row if status else key}"
    existing = _open_prs(env, branch)
    if existing:
        number = str(existing[0]["number"])
        env.sh(["gh", "pr", "edit", number, "--title", title, "--body", body])
        if not existing[0]["isDraft"]:
            env.sh(["gh", "pr", "ready", "--undo", number])
        return
    cmd = ["gh", "pr", "create", "--draft", "--base", env.config.base_branch, "--title", title, "--body", body]
    env.sh([*cmd, "--head", branch])


def _post_note(env: Env, prs: list[Pr], note: str) -> None:
    state = _read_state(env)
    opened = "\n".join(f"- {b}" for b in state.get("opened", []))
    if not opened and not note.strip():
        return
    body = f"PRs opened since the last note:\n{opened or '- none'}\n\n{note}"
    sha = hashlib.sha256(body.encode()).hexdigest()
    if state.get("note_sha") == sha:
        return
    if prs:
        body_file = _write_runtime(env, "note-body.md", body)
        env.sh(["gh", "pr", "comment", str(prs[-1].number), "--body-file", str(body_file)])
    else:
        env.notify("feature loop: no roadmap item left")
        env.log(body)
    _write_state(env, {**state, "note_sha": sha, "opened": []})


def _branch_prs(env: Env, branch: str, fields: str) -> list[dict]:
    return json.loads(env.sh(["gh", "pr", "list", "--head", branch, "--state", "all", "--json", fields]))


def _ready_prs(env: Env, branch: str) -> list[dict]:
    return [p for p in _open_prs(env, branch) if not p["isDraft"]]


def _record_opened(env: Env, branch: str) -> None:
    urls = [p["url"] for p in _branch_prs(env, branch, "number,url")] or [branch]
    state = _read_state(env)
    _write_state(env, {**state, "opened": [*state.get("opened", []), *urls]})


def _base_roadmap(env: Env) -> str:
    return env.sh(["git", "show", f"origin/{env.config.base_branch}:{_ROADMAP_FILE}"])


def _none_key(env: Env, prs: list[Pr]) -> str:
    blob = env.sh(["git", "rev-parse", f"origin/{env.config.base_branch}:{_ROADMAP_FILE}"]).strip()
    return json.dumps([blob, sorted((p.number, p.state) for p in prs)])


def _choose(env: Env, prs: list[Pr], branches: list[str]) -> tuple[Roadmap, Pick]:
    roadmap = parse_roadmap(_base_roadmap(env))
    return roadmap, choose(roadmap, branches, prs)


def _clean(env: Env) -> None:
    env.sh(["git", "reset", "--hard"])
    env.sh(["git", "clean", "-fd"])


def _local_ahead(env: Env, branch: str) -> bool:
    try:
        env.sh(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
        env.sh(["git", "merge-base", "--is-ancestor", f"origin/{branch}", branch])
        return int(env.sh(["git", "rev-list", "--count", f"origin/{branch}..{branch}"]).strip() or 0) > 0
    except subprocess.CalledProcessError:
        return False


def _checkout_resume(env: Env, branch: str) -> None:
    if _local_ahead(env, branch):
        env.sh(["git", "checkout", branch])
        env.sh(["git", "push", "-u", "origin", branch])
    else:
        env.sh(["git", "checkout", "-B", branch, f"origin/{branch}"])


def _push_if_ahead(env: Env, branch: str) -> None:
    try:
        ahead = int(env.sh(["git", "rev-list", "--count", f"origin/{branch}..HEAD"]).strip() or 0)
    except subprocess.CalledProcessError:
        ahead = 1
    if ahead:
        env.sh(["git", "push", "-u", "origin", branch])


def _drop_status(env: Env, branch: str) -> None:
    if _status_path(env).exists():
        env.sh(["git", "rm", "-q", ".loop/status.json"])
        _commit(env, branch, f"chore(loop): {branch.removeprefix('loop/')} drop status file", [])


def _fields(status: Status | None, branch: str) -> dict[str, str]:
    if status is None:
        return {"row": "", "spec": "", "plan": "", "key": branch.removeprefix("loop/"), "branch": branch}
    return {"row": status.row, "spec": status.spec, "plan": status.plan, "key": status.key, "branch": branch}


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _on_weekend(env: Env) -> bool:
    return not (env.weekend_ok or may_start(env.now()))


class _Run:
    def __init__(self, env: Env, usage: Usage) -> None:
        self.env = env
        self.usage = usage
        self.errors = 0

    def failed(self, why: str) -> str | None:
        self.errors += 1
        self.env.log(f"environment failure {self.errors}: {why}")
        if self.errors < MAX_ERRORS:
            return None
        self.env.notify(f"feature loop stopped: {why}")
        return "env"

    def once(self) -> str | None:
        if over_limit(self.usage):
            return "limit"
        if _on_weekend(self.env):
            return "weekend"
        prs, branches = _snapshot(self.env)
        _clean(self.env)
        branch = unfinished(branches, prs, _live(self.env, branches, prs))
        if branch:
            _checkout_resume(self.env, branch)
            status = read_status(_status_path(self.env))
            return self.work(branch, status, resume_stage(status))
        return self.pick(prs, branches)

    def pick(self, prs: list[Pr], branches: list[str]) -> str | None:
        env = self.env
        none_key = _none_key(env, prs)
        if _read_state(env).get("none_key") == none_key:
            return "done"
        try:
            roadmap, picked = _choose(env, prs, branches)
        except RoadmapError as e:
            return self.failed(f"roadmap: {str(e).splitlines()[0]}")
        env.sh(["git", "checkout", "--detach", f"origin/{env.config.base_branch}"])
        if picked.item is None:
            return self.nothing_left(roadmap, prs, none_key)
        status = new_status(picked.item.title, env.today)
        branch = f"loop/{status.key}"
        self.errors = 0
        env.sh(["git", "checkout", "-B", branch, f"origin/{env.config.base_branch}"])
        _save_stage(env, branch, status, "spec")
        return self.work(branch, status, "spec")

    def nothing_left(self, roadmap: Roadmap, prs: list[Pr], none_key: str) -> str:
        note = none_note(roadmap, prs)
        _write_runtime(self.env, "note.md", note)
        _post_note(self.env, prs, note)
        _write_state(self.env, {**_read_state(self.env), "none_key": none_key})
        return "done"

    def step(self, stage: str, branch: str, status: Status | None) -> StageResult:
        env = self.env
        if stage == "pr":
            spec_text = _read(env.worktree / status.spec) if status else ""
            if owner_questions(spec_text):
                return StageResult("park", f"owner questions in {status.spec}", self.usage)
            if status and not has_calls_section(spec_text):
                why = "spec has no 'Calls made for the owner' with rejected alternatives"
                return StageResult("park", why, self.usage)
            _drop_status(env, branch)
        head = env.sh(["git", "rev-parse", "HEAD"])
        env.log(f"{branch} {stage} start")
        r = parse_stream(env.claude(stage, render(stage, env, **_fields(status, branch))))
        _log_result(env, f"{branch} {stage}", r)
        _push_if_ahead(env, branch)
        if r.outcome in ("ok", "more") and stage != "pr" and env.sh(["git", "rev-parse", "HEAD"]) == head:
            return StageResult("error", "stage made no commit", r.usage)
        if r.outcome == "ok" and stage == "pr" and not _ready_prs(env, branch):
            return StageResult("error", "pr stage reported ok but no ready PR exists", r.usage)
        return r

    def work(self, branch: str, status: Status | None, stage: str) -> str | None:
        reason = "parked in an earlier run; see the branch log"
        while stage not in ("done", "parked"):
            if over_limit(self.usage):
                return "limit"
            if _on_weekend(self.env):
                return "weekend"
            r = self.step(stage, branch, status)
            self.usage = r.usage or self.usage
            if r.outcome == "usage":
                return "usage"
            if r.outcome == "error":
                stop = self.failed(f"{stage} stage: {r.detail}")
                if stop:
                    return stop
                continue
            self.errors = 0
            previous, stage = stage, next_stage(stage, r.outcome)
            reason = r.detail
            if stage != "done" and stage != previous and status:
                _save_stage(self.env, branch, status, stage)
        if stage == "parked":
            _open_draft(self.env, branch, status, reason)
        _record_opened(self.env, branch)
        return None


def _probe(env: Env) -> tuple[Usage | None, str]:
    r = parse_stream(env.claude("probe", render("probe", env)))
    _log_result(env, "probe", r)
    if r.outcome == "usage":
        return r.usage, "limit"
    if r.outcome == "error" or r.usage is None:
        why = f"probe failed: {r.detail}" if r.outcome == "error" else "probe gave no usage"
        env.log(why)
        env.notify(f"feature loop stopped: {why}")
        return r.usage, "env"
    return r.usage, "limit" if over_limit(r.usage) else ""


def run(env: Env) -> str:
    if _on_weekend(env):
        return "weekend"
    usage, stop = _probe(env)
    if stop or usage is None:
        return stop or "env"
    loop = _Run(env, usage)
    while True:
        try:
            reason = loop.once()
        except (subprocess.CalledProcessError, OSError) as e:
            reason = loop.failed(f"{' '.join(map(str, getattr(e, 'cmd', [])))}: {getattr(e, 'stderr', None) or e}")
        if reason is not None:
            return reason


def notify_command(msg: str, repo_name: str) -> list[str]:
    script = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
    return ["osascript", "-e", script, f"kit loop: {repo_name}", msg]


def _print_pick(picked: Pick) -> None:
    for skip in picked.skipped:
        print(f"skipped {skip.item.title}: {skip.reason}")
    print(f"pick {picked.item.title}" if picked.item else "none")


def pick_only(env: Env) -> str:
    if _on_weekend(env):
        return "weekend"
    prs, branches = _snapshot(env)
    try:
        _, picked = _choose(env, prs, branches)
    except RoadmapError as e:
        env.log(f"roadmap: {str(e).splitlines()[0]}")
        return "env"
    _print_pick(picked)
    return "done"


def guarded(env: Env, action: Callable[[Env], str]) -> int:
    try:
        reason = action(env)
    except Exception:
        env.log(traceback.format_exc())
        env.notify(f"kit loop crashed; see {env.runtime}/loop.log")
        return 1
    env.log(f"stopped: {reason}")
    return 0
