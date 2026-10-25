"""UNIT: kit.loop.driver, over claude stream lines and git/gh answers built in code."""

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from kit.kitfile import LoopConfig
from kit.loop.driver import (
    CO_AUTHOR,
    Env,
    _checkout_resume,
    _Run,
    acquire_lock,
    guarded,
    notify_command,
    pick_only,
    render,
    run,
)
import pytest

from kit.loop.ledger import StageEntry, StopEntry, read_ledger
from kit.loop.prs import ATTRIBUTION, Pr, parse_park_body
from kit.loop.state import Status, read_status, write_status
from kit.loop.stream import Usage

ROADMAP_A_OPEN = "### Row A\n- Status: open\n"
ROADMAP_A_AND_B_OPEN = "### Row A\n- Status: open\n\n### Row B\n- Status: open\n"
ROADMAP_A_ACTIVE = "### Row A\n- Status: active\n"
ROADMAP_OWNER = "### Row B\n- Status: owner\n- Blocked by: needs owner\n"
GOOD_SPEC = "# Spec\n\n## Calls made for the owner\n\n- Chose X. Rejected: Y.\n"
FRIDAY = datetime(2026, 10, 23, 10)
FRIDAY_LATE = datetime(2026, 10, 23, 23)
SATURDAY_EARLY = datetime(2026, 10, 24, 0, 5)
SUNDAY = datetime(2026, 10, 25, 10)


def rate(five: float, seven: float = 0.1, status: str = "allowed") -> str:
    windows = {"five_hour": {"utilization": five}, "seven_day": {"utilization": seven}}
    info = {"status": status, "unifiedWindows": windows}
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": info})


def result(text: str, is_error: bool = False, api: int | None = None) -> str:
    return json.dumps({"type": "result", "is_error": is_error, "api_error_status": api, "result": text})


def step(text: str = "LOOP: ok", five: float = 0.1, commit: bool = True, opens: bool = False, raw=None) -> dict:
    return {"lines": raw or [rate(five), result(text)], "commit": commit, "opens": opens}


def fail_step() -> dict:
    return step(raw=[result("boom", True)], commit=False)


def usage_step(commit: bool = False) -> dict:
    return step(raw=[rate(0.2, status="rejected"), result("limit", True, 429)], commit=commit)


class FakeEnv:
    def __init__(
        self,
        tmp_path: Path,
        scripts: dict,
        prs=(),
        branches=(),
        roadmap: str = ROADMAP_A_OPEN,
        spec_text: str | None = GOOD_SPEC,
        config: LoopConfig | None = None,
        now: Callable[[], datetime] | None = None,
        saturday_after: str | None = None,
        weekend_ok: bool = False,
    ):
        self.worktree = tmp_path / "wt"
        self.runtime = tmp_path / "runtime"
        self.worktree.mkdir(parents=True, exist_ok=True)
        self.today = "2026-10-17"
        self.now_fn = now
        self.saturday_after = saturday_after
        self.weekend_ok = weekend_ok
        self.config = config or LoopConfig("develop")
        self.roadmap = roadmap
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.prs = list(prs)
        self.branches = list(branches)
        self.spec_text = spec_text
        self.cmds: list[list[str]] = []
        self.stages: list[str] = []
        self.notices: list[str] = []
        self.logs: list[str] = []
        self.head = 0
        self.branch = ""
        self.committed = ""
        self.fail_on: str | None = None
        self.pushed = 0
        self.local_ahead = 0
        self.trace: list[str] = []
        self.tips: dict[str, str] = {}

    @property
    def state(self) -> Path:
        return self.runtime / "state.json"

    def add_pr(self, draft: bool = False, body: str = "") -> None:
        n = len(self.prs) + 1
        self.prs.append(Pr(n, self.branch, "OPEN", f"2026-10-17T10:{n:02d}", f"https://x/pull/{n}", "", draft, body))

    def claude(self, stage: str, text: str) -> list[str]:
        self.stages.append(stage)
        self.trace.append(f"claude:{stage}")
        queue = self.scripts.get(stage)
        s = queue.pop(0) if queue else step(raw=[result("unscripted stage", True)], commit=False)
        self.head += s["commit"]
        if s["opens"]:
            self.add_pr()
        if stage == "spec" and self.spec_text is not None:
            status = read_status(self.worktree / ".loop" / "status.json")
            path = self.worktree / status.spec
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.spec_text)
        return s["lines"]

    def clock(self) -> datetime:
        if self.now_fn:
            return self.now_fn()
        if self.saturday_after:
            return SATURDAY_EARLY if self.saturday_after in self.stages else FRIDAY_LATE
        return FRIDAY

    def blob(self) -> str:
        return hashlib.sha1(self.roadmap.encode()).hexdigest()

    def pr_rows(self, cmd: list[str]) -> str:
        rows = [
            {"number": p.number, "headRefName": p.head, "state": p.state, "createdAt": p.created, "url": p.url,
             "title": p.title, "isDraft": p.is_draft, "body": p.body}
            for p in self.prs
        ]
        if "--head" in cmd:
            rows = [r for r in rows if r["headRefName"] == cmd[cmd.index("--head") + 1]]
        if cmd[cmd.index("--state") + 1 :][:1] == ["open"]:
            rows = [r for r in rows if r["state"] == "OPEN"]
        return json.dumps(rows)

    def sh(self, cmd: list[str]) -> str:
        self.cmds.append(cmd)
        line = " ".join(cmd)
        self.trace.append(line)
        base = self.config.base_branch
        if self.fail_on and line.startswith(self.fail_on):
            self.fail_on = None
            raise subprocess.CalledProcessError(1, cmd, stderr="boom: network down")
        if line == f"git show origin/{base}:docs/roadmap.md":
            return self.roadmap
        if line == f"git rev-parse origin/{base}:docs/roadmap.md":
            return self.blob() + "\n"
        if line.startswith("gh pr list"):
            return self.pr_rows(cmd)
        if line.startswith("git show origin/"):
            branch = cmd[2].removeprefix("origin/").split(":", 1)[0]
            if branch not in self.tips:
                raise subprocess.CalledProcessError(128, cmd, stderr="path does not exist")
            return self.tips[branch]
        if line.startswith("git rev-list"):
            return str(self.local_ahead if not line.endswith("..HEAD") else int(self.head != self.pushed))
        if line.startswith("git rm"):
            (self.worktree / ".loop" / "status.json").unlink()
            self.tips.pop(self.branch, None)
        if line.startswith("git ls-remote"):
            return "\n".join(f"abc\trefs/heads/{b}" for b in self.branches)
        if line == "git rev-parse HEAD":
            return str(self.head)
        if line.startswith(("git checkout -b", "git checkout -B")):
            self.branch = cmd[3]
            self.pushed = self.head
        elif line.startswith("git checkout loop/"):
            self.branch = cmd[2]
        if line.startswith("git commit"):
            status = self.worktree / ".loop" / "status.json"
            saved = status.read_text() if status.exists() else "removed"
            if saved == self.committed:
                raise subprocess.CalledProcessError(1, cmd, stderr="nothing to commit")
            self.committed = saved
        if line.startswith("git push"):
            self.pushed = self.head
            pushed_status = self.worktree / ".loop" / "status.json"
            if pushed_status.exists() and self.branch in self.tips:
                self.tips[self.branch] = pushed_status.read_text()
            if self.branch not in self.branches:
                self.branches.append(self.branch)
        if line.startswith("gh pr create"):
            if any(p.head == cmd[cmd.index("--head") + 1] and p.state == "OPEN" for p in self.prs):
                raise subprocess.CalledProcessError(1, cmd, stderr="a pull request for this branch already exists")
            body = cmd[cmd.index("--body") + 1] if "--body" in cmd else ""
            self.add_pr("--draft" in cmd, body)
        if line.startswith("gh pr edit"):
            number = int(cmd[3])
            self.prs = [replace(p, body=cmd[cmd.index("--body") + 1], title=cmd[cmd.index("--title") + 1]) if p.number == number else p for p in self.prs]
        if line.startswith("gh pr ready --undo"):
            number = int(cmd[4])
            self.prs = [replace(p, is_draft=True) if p.number == number else p for p in self.prs]
        return ""

    def env(self) -> Env:
        return Env(
            claude=self.claude,
            sh=self.sh,
            notify=self.notices.append,
            log=self.logs.append,
            worktree=self.worktree,
            runtime=self.runtime,
            today=self.today,
            now=self.clock,
            weekend_ok=self.weekend_ok,
            config=self.config,
            test_command="uv run pytest -q",
            repo_name="demo",
        )

    def lines(self) -> list[str]:
        return [" ".join(c) for c in self.cmds]

    def drafts(self) -> list[list[str]]:
        return [c for c in self.cmds if c[:4] == ["gh", "pr", "create", "--draft"]]

    def comments(self) -> list[list[str]]:
        return [c for c in self.cmds if c[:3] == ["gh", "pr", "comment"]]


def env_with(config: LoopConfig, runtime: Path = Path("/runtime")) -> Env:
    """An Env for rendering prompts: nothing in it touches the disk."""
    fake = FakeEnv.__new__(FakeEnv)
    fake.runtime, fake.worktree, fake.today, fake.config = runtime, Path("/wt"), "2026-10-17", config
    fake.now_fn, fake.saturday_after, fake.weekend_ok = None, None, False
    fake.notices, fake.logs = [], []
    return fake.env()


def scripts(**more) -> dict:
    return {"probe": [step(commit=False)], **more}


def run_fake(
    tmp_path,
    roadmap: str = ROADMAP_A_OPEN,
    prs=(),
    branches=(),
    spec_text=GOOD_SPEC,
    resume_branch: str | None = None,
    open_prs=(),
    stage: str = "build",
    now: Callable[[], datetime] | None = None,
    saturday_after: str | None = None,
    weekend_ok: bool = False,
    **stages,
):
    """Run the loop; resume_branch starts it on a live branch at `stage`, holding the open_prs given as gh rows."""
    if resume_branch:
        roadmap, branches = ROADMAP_A_ACTIVE, [*branches, resume_branch]
        stages = {"pr": [step(commit=False), step(commit=False)], **stages}
    f = FakeEnv(
        tmp_path,
        scripts(**stages),
        prs=prs,
        branches=branches,
        roadmap=roadmap,
        spec_text=spec_text,
        now=now,
        saturday_after=saturday_after,
        weekend_ok=weekend_ok,
    )
    if resume_branch:
        f.tips[resume_branch] = json.dumps({"stage": stage})
        resume_status(f, stage)
        for row in open_prs:
            f.branch = resume_branch
            f.prs.append(Pr(row["number"], resume_branch, "OPEN", f"2026-10-17T10:{row['number']:02d}", "u", "", row["isDraft"]))
    return run(f.env()), f


def full_item(tmp_path, spec_text=GOOD_SPEC) -> tuple[str, FakeEnv]:
    return run_fake(
        tmp_path,
        spec_text=spec_text,
        spec=[step()],
        plan=[step()],
        build=[step("LOOP: more"), step()],
        pr=[step("LOOP: ok https://x/pull/1", commit=False, opens=True)],
    )


def resume_status(f: FakeEnv, stage: str = "build") -> None:
    (f.worktree / ".loop").mkdir()
    write_status(f.worktree / ".loop" / "status.json", Status("a", "Row A", stage, "spec.md", "plan.md"))
    (f.worktree / "spec.md").write_text(GOOD_SPEC)


def test_stops_at_limit_before_any_work(tmp_path):
    f = FakeEnv(tmp_path, {"probe": [step(five=0.85, commit=False)]})
    assert run(f.env()) == "limit"
    assert f.cmds == [] and f.stages == ["probe"]


def test_picks_the_first_open_item_of_the_base_roadmap(tmp_path):
    reason, fake = run_fake(tmp_path, roadmap=ROADMAP_A_OPEN)
    assert any(c[:4] == ["git", "checkout", "-B", "loop/row-a"] for c in fake.cmds)


def test_invalid_roadmap_is_an_env_failure_naming_the_line(tmp_path):
    reason, fake = run_fake(tmp_path, roadmap="### A\n- Status: soon\n")
    assert reason == "env" and fake.stages == ["probe"]  # two failed picks in a row stop the run
    assert any("roadmap: docs/roadmap.md:1:" in m for m in fake.notices)


def test_a_failed_roadmap_read_is_retried_once(tmp_path):
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    f.fail_on = "git show origin/develop:docs/roadmap.md"
    assert run(f.env()) == "done"  # one failure is retried, and the second read works
    assert any("network down" in m for m in f.logs)


def test_a_pick_makes_no_claude_call(tmp_path):
    reason, f = run_fake(tmp_path, roadmap=ROADMAP_OWNER)
    assert reason == "done" and f.stages == ["probe"]


def test_resumes_unfinished_branch_before_picking(tmp_path):
    f = FakeEnv(tmp_path, scripts(build=[step()], pr=[step(opens=True)]), branches=["loop/a"], roadmap=ROADMAP_A_ACTIVE)
    resume_status(f)
    assert run(f.env()) == "done"
    assert f.stages == ["probe", "build", "pr"]
    assert "git checkout -B loop/a origin/loop/a" in f.lines()


def test_full_item_then_nothing_left(tmp_path):
    reason, f = full_item(tmp_path)
    assert reason == "done"
    assert f.stages == ["probe", "spec", "plan", "build", "build", "pr"]
    assert "git checkout -B loop/row-a origin/develop" in f.lines()
    comments = f.comments()
    assert len(comments) == 1 and comments[0][3] == "1" and "--body-file" in comments[0]
    assert json.loads(f.state.read_text())["opened"] == []


def test_the_note_files_and_state_live_in_the_runtime_directory(tmp_path):
    reason, f = full_item(tmp_path)
    body = Path(f.comments()[0][f.comments()[0].index("--body-file") + 1])
    assert body == f.runtime / "note-body.md" and "https://x/pull/1" in body.read_text()
    assert f.state.parent == f.runtime and not (f.worktree / "data").exists()


def test_opened_branch_is_in_the_note(tmp_path):
    prs = [Pr(1, "loop/z", "OPEN", "2026-10-16T01", "u")]
    f = FakeEnv(tmp_path, scripts(), prs=prs, roadmap=ROADMAP_OWNER)
    f.runtime.mkdir()
    f.state.write_text(json.dumps({"opened": ["https://x/pull/9"]}))
    assert run(f.env()) == "done"
    text = Path(f.comments()[0][f.comments()[0].index("--body-file") + 1]).read_text()
    assert "https://x/pull/9" in text and "- Row B: needs owner" in text
    assert (f.runtime / "note.md").read_text().startswith("## Waiting on the owner")


def test_a_blank_note_with_nothing_opened_posts_nothing(tmp_path):
    prs = [Pr(1, "loop/z", "MERGED", "2026-10-16T01", "u")]
    f = FakeEnv(tmp_path, scripts(), prs=prs, roadmap=ROADMAP_A_ACTIVE)
    assert run(f.env()) == "done"
    assert f.comments() == [] and f.notices == []
    assert "none_key" in json.loads(f.state.read_text())


def test_a_blank_note_with_nothing_opened_and_no_pr_does_not_notify(tmp_path):
    reason, f = run_fake(tmp_path, roadmap=ROADMAP_A_ACTIVE)
    assert reason == "done" and f.notices == [] and f.comments() == []


def test_stops_between_stages_at_limit(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step(five=0.81)])
    assert reason == "limit" and "plan" not in f.stages


def test_usage_stops_without_parking(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step()], plan=[step()], build=[usage_step()])
    assert reason == "usage" and f.drafts() == []
    assert read_status(f.worktree / ".loop" / "status.json").stage == "build"


def test_two_errors_in_a_row_notify_and_stop(tmp_path):
    reason, f = run_fake(tmp_path, spec=[fail_step(), fail_step()])
    assert reason == "env" and len(f.notices) == 1 and f.drafts() == []


def test_one_error_then_success_continues(tmp_path):
    reason, f = run_fake(tmp_path, spec=[fail_step(), step()], plan=[step()], build=[step()], pr=[step(opens=True)])
    assert reason == "done" and f.notices == [] and f.stages.count("spec") == 2


def test_stage_without_new_commit_is_error(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step(commit=False), step(commit=False)])
    assert reason == "env" and len(f.notices) == 1


def test_park_opens_a_draft_pr_and_moves_on(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step()], plan=[step("LOOP: park tests red")])
    assert reason == "done"
    (draft,) = f.drafts()
    body = draft[draft.index("--body") + 1]
    assert parse_park_body(body).reason == "tests red" and body.endswith(ATTRIBUTION + "\n")
    assert "Spec: docs/superpowers/specs/2026-10-17-row-a-design.md" in body
    assert "Plan: docs/superpowers/plans/2026-10-17-row-a.md" in body
    assert json.loads(f.state.read_text())["opened"] == []  # cleared by the note that followed
    assert "build" not in f.stages


def test_a_resumed_item_that_parks_again_edits_its_open_draft(tmp_path):
    questions = "# Spec\n\n## Questions for the owner\n- New question? Recommended: yes\n"
    f = FakeEnv(tmp_path, scripts(), branches=["loop/a"], roadmap=ROADMAP_A_ACTIVE, spec_text=questions)
    resume_status(f, "pr")
    (f.worktree / "spec.md").write_text(questions)
    f.tips["loop/a"] = json.dumps({"stage": "pr"})
    f.branch = "loop/a"
    f.add_pr(draft=True, body="old body")
    assert run(f.env()) == "done"
    assert f.drafts() == []
    (edit,) = [c for c in f.cmds if c[:3] == ["gh", "pr", "edit"]]
    assert edit[3] == "1" and edit[edit.index("--title") + 1] == "loop (parked): Row A"
    body = edit[edit.index("--body") + 1]
    assert parse_park_body(body).questions == ("New question? Recommended: yes",)
    assert not any("environment failure" in m for m in f.logs)
    assert json.loads(f.state.read_text())["opened"] == []  # recorded, then cleared by the note


def test_re_parking_a_head_whose_draft_was_marked_ready_puts_it_back_to_draft(tmp_path):
    questions = "# Spec\n\n## Questions for the owner\n- Q?\n"
    f = FakeEnv(tmp_path, scripts(), branches=["loop/a"], roadmap=ROADMAP_A_ACTIVE, spec_text=questions)
    resume_status(f, "pr")
    (f.worktree / "spec.md").write_text(questions)
    f.tips["loop/a"] = json.dumps({"stage": "pr"})
    f.branch = "loop/a"
    f.add_pr(draft=False)
    run(f.env())
    assert "gh pr ready --undo 1" in f.lines() and f.drafts() == []


def test_the_parked_draft_names_the_configured_base_branch(tmp_path):
    f = FakeEnv(tmp_path, scripts(spec=[step()], plan=[step("LOOP: park x")]), config=LoopConfig("main"))
    f.roadmap = ROADMAP_A_OPEN
    run(f.env())
    (draft,) = f.drafts()
    assert draft[draft.index("--base") + 1] == "main" and "origin/main" in " ".join(f.lines())
    assert draft[draft.index("--title") + 1] == "loop (parked): Row A"
    assert draft[draft.index("--head") + 1] == "loop/row-a"


def test_the_parked_note_lists_the_draft_and_its_reason(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step()], plan=[step("LOOP: park tests red")])
    text = (f.runtime / "note.md").read_text()
    assert "## Parked loop PRs" in text and "- https://x/pull/1: tests red" in text


def test_parked_branch_is_recorded_as_opened(tmp_path):
    # Row B fails twice, so no note clears "opened" after Row A parks.
    reason, f = run_fake(
        tmp_path,
        roadmap=ROADMAP_A_AND_B_OPEN,
        spec=[step(), fail_step(), fail_step()],
        plan=[step("LOOP: park x")],
    )
    assert reason == "env"
    assert json.loads(f.state.read_text())["opened"] == ["https://x/pull/1"]


def test_pr_without_calls_section_parks(tmp_path):
    reason, f = run_fake(tmp_path, spec_text="# Spec\n", spec=[step()], plan=[step()], build=[step()])
    assert reason == "done"
    assert len(f.drafts()) == 1 and "pr" not in f.stages


def test_final_note_posted_once(tmp_path):
    pr = Pr(1, "loop/z", "MERGED", "2026-10-16T01", "u")
    counts = []
    for _ in range(2):
        f = FakeEnv(tmp_path, scripts(), prs=[pr], roadmap=ROADMAP_OWNER)
        assert run(f.env()) == "done"
        counts.append(len(f.comments()))
    assert counts == [1, 0]


def test_note_without_any_loop_pr_goes_to_notify(tmp_path):
    reason, f = run_fake(tmp_path, roadmap=ROADMAP_OWNER)
    assert reason == "done" and len(f.notices) == 1


def test_acquire_lock_is_exclusive(tmp_path):
    path = tmp_path / "d" / "lock"
    first = acquire_lock(path)
    assert first is not None and acquire_lock(path) is None
    first.close()
    assert acquire_lock(path) is not None


def test_render_replaces_fields_and_leaves_no_placeholder(tmp_path):
    env = env_with(LoopConfig("develop"))
    text = render("build", env, plan="P.md", row="R", spec="S", key="k")
    assert "P.md" in text and "{plan}" not in text
    for stage in ("probe", "spec", "plan", "build", "pr"):
        text = render(stage, env, row="R", key="k", branch="loop/k", spec="s", plan="p")
        assert "LOOP:" in text and "{" not in text


def test_render_uses_the_test_command_and_leaves_field_values_alone(tmp_path):
    env = env_with(LoopConfig("develop"))
    env.test_command = "make {check}"
    assert "`make {check}`" in render("pr", env, row="R", key="k", branch="loop/k", spec="s", plan="p")


def test_build_more_does_not_recommit_unchanged_status(tmp_path):
    reason, f = full_item(tmp_path)
    assert reason == "done"
    assert f.lines().count("git commit -m chore(loop): row-a stage build\n\n" + CO_AUTHOR) == 1


def test_sh_failure_counts_as_env_failure_and_is_logged(tmp_path):
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    f.fail_on = "git fetch"
    assert run(f.env()) == "done"
    assert any("network down" in m for m in f.logs)


def test_two_sh_failures_notify_and_stop(tmp_path):
    f = FakeEnv(tmp_path, scripts())
    f.fail_on = "git fetch"
    env = f.env()
    real = env.sh

    def always_fail(cmd):
        if cmd[:2] == ["git", "fetch"]:
            f.cmds.append(cmd)
            raise subprocess.CalledProcessError(1, cmd, stderr="down")
        return real(cmd)

    env.sh = always_fail
    assert run(env) == "env" and len(f.notices) == 1


def test_notify_script_takes_title_and_text_as_argv():
    cmd = notify_command('say "hi" \\ now', "demo")
    assert cmd[0] == "osascript" and cmd[-1] == 'say "hi" \\ now' and cmd[-2] == "kit loop: demo"
    assert "display notification" in cmd[2] and 'say "hi"' not in cmd[2] and "demo" not in cmd[2]


def test_push_follows_each_build_batch(tmp_path):
    reason, f = full_item(tmp_path)
    assert reason == "done"
    t = f.trace
    for i in [i for i, c in enumerate(t) if c == "claude:build"]:
        assert t[i + 1] == "git rev-list --count origin/loop/row-a..HEAD"
        assert t[i + 2] == "git push -u origin loop/row-a"


def test_push_follows_a_usage_stop_with_commits(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step()], plan=[step()], build=[usage_step(commit=True)])
    assert reason == "usage"
    assert f.trace[-1] == "git push -u origin loop/row-a" and f.pushed == f.head


def test_no_push_when_nothing_is_ahead(tmp_path):
    reason, f = run_fake(tmp_path, spec=[step()], plan=[step()], build=[usage_step()])
    after = f.trace[f.trace.index("claude:build") :]
    assert reason == "usage" and not any(c.startswith("git push") for c in after)


def test_pr_stage_drops_status_file_and_pushes_before_the_session(tmp_path):
    reason, f = full_item(tmp_path)
    t = f.trace
    i = t.index("claude:pr")
    assert t[i - 4 : i - 1] == [
        "git rm -q .loop/status.json",
        "git commit -m chore(loop): row-a drop status file\n\n" + CO_AUTHOR,
        "git push -u origin loop/row-a",
    ]


def test_pr_ok_without_a_pr_is_a_failure(tmp_path):
    reason, f = run_fake(
        tmp_path, spec=[step()], plan=[step()], build=[step()], pr=[step(commit=False), step(commit=False)]
    )
    assert reason == "env" and any("no ready PR exists" in m for m in f.logs)


def test_none_key_skips_the_pick_until_the_roadmap_or_prs_change(tmp_path):
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    assert run(f.env()) == "done"
    first_key = json.loads(f.state.read_text())["none_key"]
    again = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    assert run(again.env()) == "done" and again.comments() == [] and again.notices == []
    merged = Pr(1, "loop/z", "MERGED", "2026-10-16T01", "u")
    changed_prs = FakeEnv(tmp_path, scripts(), prs=[merged], roadmap=ROADMAP_OWNER)
    assert run(changed_prs.env()) == "done" and json.loads(changed_prs.state.read_text())["none_key"] != first_key
    assert any(c[:2] == ["git", "show"] for c in changed_prs.cmds)  # it read the roadmap again


def test_a_changed_roadmap_blob_runs_the_pick_again(tmp_path):
    first = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    assert run(first.env()) == "done" and first.notices
    second = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER + "\n### Row C\n- Status: blocked\n- Blocked by: Row B\n")
    assert run(second.env()) == "done" and len(second.notices) == 1


def test_resume_cleans_the_worktree_first_and_pushes_a_local_branch_that_is_ahead(tmp_path):
    f = FakeEnv(tmp_path, scripts(build=[step()], pr=[step(opens=True)]), branches=["loop/a"], roadmap=ROADMAP_A_ACTIVE)
    resume_status(f)
    f.local_ahead = 2
    assert run(f.env()) == "done"
    lines = f.lines()
    assert lines.index("git reset --hard") < lines.index("git clean -fd") < lines.index("git checkout loop/a")
    assert lines.index("git checkout loop/a") + 1 == lines.index("git push -u origin loop/a")
    assert "git checkout -B loop/a origin/loop/a" not in lines


def test_resume_resets_to_origin_when_local_is_not_ahead(tmp_path):
    f = FakeEnv(tmp_path, scripts(), branches=["loop/a"])
    loop = _Run(f.env(), Usage(0.1, 0.1))
    _checkout_resume(loop.env, "loop/a")
    assert f.lines()[-1] == "git checkout -B loop/a origin/loop/a"


def test_resumes_a_live_branch_whose_pr_was_merged_by_hand(tmp_path):
    merged = Pr(1, "loop/a", "MERGED", "2026-10-17T01", "u1")
    scripted = scripts(build=[step()], pr=[step(opens=True)])
    f = FakeEnv(tmp_path, scripted, prs=[merged], branches=["loop/a"], roadmap=ROADMAP_A_ACTIVE)
    f.tips["loop/a"] = json.dumps({"stage": "build"})
    resume_status(f)
    assert run(f.env()) == "done"
    assert f.stages == ["probe", "build", "pr"]
    assert "git show origin/loop/a:.loop/status.json" in f.lines()
    assert "git show origin/develop:docs/roadmap.md" in f.lines()  # the run went on to the code pick


def test_pr_ok_needs_an_open_pr_not_an_old_merged_one(tmp_path):
    merged = Pr(1, "loop/a", "MERGED", "2026-10-17T01", "u1")
    scripted = scripts(pr=[step(commit=False), step(commit=False)])
    f = FakeEnv(tmp_path, scripted, prs=[merged], branches=["loop/a"], roadmap=ROADMAP_A_ACTIVE)
    f.tips["loop/a"] = json.dumps({"stage": "pr"})
    resume_status(f, "pr")
    assert run(f.env()) == "env" and any("no ready PR exists" in m for m in f.logs)


def test_spec_with_owner_questions_parks_with_them_in_the_draft(tmp_path):
    spec = GOOD_SPEC + "\n## Questions for the owner\n- Include REITs? Recommended: no\n"
    reason, fake = full_item(tmp_path, spec_text=spec)
    body = fake.drafts()[-1][fake.drafts()[-1].index("--body") + 1]
    assert "owner questions in" in body and "- Include REITs? Recommended: no" in body
    assert "pr" not in fake.stages
    assert parse_park_body(body).questions == ("Include REITs? Recommended: no",)


def test_owner_questions_park_before_the_calls_check(tmp_path):
    spec = "# Spec\n\n## Questions for the owner\n- Cap?\n"
    reason, fake = full_item(tmp_path, spec_text=spec)
    body = fake.drafts()[-1][fake.drafts()[-1].index("--body") + 1]
    assert "Parked: owner questions in docs/superpowers/specs/2026-10-17-row-a-design.md" in body


def test_an_answered_spec_with_an_empty_questions_section_goes_on_to_the_pr(tmp_path):
    reason, fake = full_item(tmp_path, spec_text=GOOD_SPEC + "\n## Questions for the owner\n\n")
    assert fake.drafts() == [] and "pr" in fake.stages


def test_pr_stage_with_only_a_draft_open_is_a_failure(tmp_path):
    reason, fake = run_fake(tmp_path, resume_branch="loop/row-a", open_prs=[{"number": 3, "isDraft": True}], stage="pr")
    assert any("pr stage reported ok but no ready PR exists" in line for line in fake.logs)
    assert "gh pr list --head loop/row-a --state open --json number,isDraft" in fake.lines()


def test_pr_stage_with_a_ready_pr_open_is_done(tmp_path):
    reason, fake = run_fake(
        tmp_path,
        resume_branch="loop/row-a",
        open_prs=[{"number": 3, "isDraft": True}, {"number": 4, "isDraft": False}],
        stage="pr",
        pr=[step(commit=False)],
    )
    assert reason == "done" and not any("no ready PR" in m for m in fake.logs)


def test_spec_prompt_asks_for_the_three_piles_and_finishes_an_answered_spec(tmp_path):
    text = render("spec", env_with(LoopConfig("develop")), row="R", spec="docs/s.md")
    assert "## Questions for the owner" in text and "LOOP: park owner questions" in text
    assert "If `docs/s.md` already exists, the owner answered its questions in it" in text and "{" not in text


def test_pr_prompt_readies_an_existing_draft_instead_of_creating(tmp_path):
    text = render("pr", env_with(LoopConfig("develop")), row="R", key="r", branch="loop/r", spec="s", plan="p")
    assert "gh pr edit loop/r --title" in text and "--body-file" in text and "gh pr ready loop/r" in text
    assert "{" not in text


def test_probe_error_is_an_env_failure_with_detail_and_one_notice(tmp_path):
    f = FakeEnv(tmp_path, {"probe": [step(raw=[result("claude exited 1: bad flag", True)], commit=False)]})
    assert run(f.env()) == "env"
    assert len(f.notices) == 1 and any("bad flag" in m for m in f.logs) and f.cmds == []


def test_probe_without_usage_is_an_env_failure(tmp_path):
    f = FakeEnv(tmp_path, {"probe": [step(raw=[result("LOOP: ok")], commit=False)]})
    assert run(f.env()) == "env" and len(f.notices) == 1


def test_guarded_logs_a_crash_notifies_and_returns_1(tmp_path):
    f = FakeEnv(tmp_path, scripts())

    def boom(_env) -> str:
        raise RuntimeError("kaput")

    assert guarded(f.env(), boom) == 1
    assert len(f.notices) == 1 and any("kaput" in m for m in f.logs)
    assert f.notices[0] == f"kit loop crashed; see {f.runtime}/loop.log"
    assert guarded(f.env(), lambda _e: "done") == 0


def test_prompts_forbid_git_moves_and_pr_stage_runs_the_suite(tmp_path):
    env = env_with(LoopConfig("develop"))
    for stage in ("spec", "plan", "build"):
        assert "worktrees" in render(stage, env) and "push" in render(stage, env)
    pr = render("pr", env, branch="loop/a")
    assert "gh pr create --base develop --head loop/a" in pr and "git rm" not in pr and "LOOP: park" in pr
    assert "`uv run pytest -q`" in pr


def test_prompts_name_the_configured_base_and_forbidden_paths(tmp_path):
    text = render("pr", env_with(LoopConfig("main", ("../a", "../b"))), row="R", key="r", branch="loop/r", spec="s", plan="p")
    assert "--base main" in text and "never write `../a` or `../b`" in text and "{" not in text


def test_rules_leave_out_never_write_without_forbidden_paths_and_join_three(tmp_path):
    none = render("build", env_with(LoopConfig("develop")))
    assert "never write" not in none and "never merge or force-push" in none and CO_AUTHOR in none
    three = render("build", env_with(LoopConfig("develop", ("a", "b", "c"))))
    assert "never write `a`, `b` or `c`;" in three
    one = render("build", env_with(LoopConfig("develop", ("a",))))
    assert "never write `a`;" in one


def test_every_stage_prompt_carries_the_commit_trailer(tmp_path):
    env = env_with(LoopConfig("develop"))
    assert CO_AUTHOR == "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    for stage in ("spec", "plan", "build", "pr"):
        assert CO_AUTHOR in render(stage, env)


def test_spec_prompt_reads_the_configured_files_and_names_the_domain_expert(tmp_path):
    plain = render("spec", env_with(LoopConfig("develop")), row="R", spec="S")
    assert "the domain expert CLAUDE.md describes" in plain and "Read these first" not in plain
    config = LoopConfig("develop", read_first=("docs/a.md", "docs/b.md"))
    text = render("spec", env_with(config), row="R", spec="S")
    assert "`docs/a.md`" in text and "`docs/b.md`" in text
    for dgi in ("investor", "GOLD_SCHEMA", "dgi"):
        assert dgi not in text


def test_pr_prompt_numbers_the_checklist_between_the_test_run_and_the_create(tmp_path):
    config = LoopConfig("develop", pr_checklist=("Update the guide.", "Bump the changelog."))
    text = render("pr", env_with(config), row="R", key="r", branch="loop/r", spec="s", plan="p")
    assert text.index("1. Run `uv run pytest -q`") < text.index("2. Update the guide.")
    assert text.index("2. Update the guide.") < text.index("3. Bump the changelog.")
    assert text.index("3. Bump the changelog.") < text.index("4. ") < text.index("gh pr create --base develop")
    plain = render("pr", env_with(LoopConfig("develop")), row="R", key="r", branch="loop/r", spec="s", plan="p")
    assert "2. " in plain and "\n\n\n" not in plain


def test_pr_prompt_writes_the_body_to_the_runtime_and_ends_it_with_the_attribution(tmp_path):
    env = env_with(LoopConfig("develop"), tmp_path / "rt")
    text = render("pr", env, row="R", key="r", branch="loop/r", spec="s", plan="p")
    assert text.count(f"{tmp_path}/rt/pr-body.md") == 3 and "--body-file" in text
    assert "the user's view" in text and "investor" not in text and ATTRIBUTION in text


def test_pr_prompt_sets_the_roadmap_item_done_after_the_pr(tmp_path):
    text = render("pr", env_with(LoopConfig("develop")), row="Row A", key="row-a", branch="loop/row-a", spec="S.md", plan="P.md")
    after = text[text.index("gh pr create") :]
    assert "docs/roadmap.md" in after and "Status: done" in after
    assert "Spec" in after and "Plan" in after and "PR" in after and "commit" in after


def test_each_stage_logs_start_and_outcome_with_usage(tmp_path):
    reason, f = full_item(tmp_path)
    assert "loop/row-a spec start" in f.logs
    assert any(m.startswith("loop/row-a spec ok") and "five_hour=" in m and "seven_day=" in m for m in f.logs)
    assert any(m.startswith("probe ok") and "five_hour=" in m for m in f.logs)


def test_pick_only_prints_the_pick_and_makes_no_claude_call(tmp_path, capsys):
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_A_AND_B_OPEN)
    assert pick_only(f.env()) == "done"
    assert capsys.readouterr().out.splitlines()[-1] == "pick Row A"
    assert f.stages == [] and not any(c[:2] == ["git", "checkout"] for c in f.cmds)


def test_pick_only_says_none_and_names_skips(tmp_path, capsys):
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER, prs=[Pr(1, "loop/z", "MERGED", "c", "u")])
    assert pick_only(f.env()) == "done"
    assert capsys.readouterr().out.splitlines() == ["none"]


def test_pick_only_reports_an_invalid_roadmap(tmp_path):
    f = FakeEnv(tmp_path, scripts(), roadmap="### A\n- Status: soon\n")
    assert pick_only(f.env()) == "env" and any("roadmap: docs/roadmap.md:1:" in m for m in f.logs)


def test_sunday_run_makes_no_claude_call(tmp_path):
    reason, fake = run_fake(tmp_path, now=lambda: SUNDAY)
    assert reason == "weekend" and fake.stages == []


def test_stage_ending_on_saturday_is_followed_by_none(tmp_path):
    # FakeEnv.clock returns Friday 23:00 until its claude() has run the spec stage, then Saturday 00:05
    reason, fake = run_fake(tmp_path, saturday_after="spec", spec=[step()])
    assert reason == "weekend" and fake.stages == ["probe", "spec"]
    assert read_status(fake.worktree / ".loop" / "status.json").stage == "plan"


def test_item_finishing_on_saturday_picks_no_next_item(tmp_path):
    reason, fake = run_fake(
        tmp_path,
        roadmap=ROADMAP_A_AND_B_OPEN,
        saturday_after="pr",
        spec=[step()],
        plan=[step()],
        build=[step()],
        pr=[step("LOOP: ok https://x/pull/1", commit=False, opens=True)],
    )
    assert reason == "weekend" and fake.stages == ["probe", "spec", "plan", "build", "pr"]
    assert not any("loop/row-b" in line for line in fake.lines())


def test_weekend_ok_overrides(tmp_path):
    reason, fake = run_fake(tmp_path, now=lambda: SUNDAY, weekend_ok=True)
    assert "spec" in fake.stages


def test_pick_only_on_sunday_is_weekend_without_reading_the_roadmap(tmp_path):
    f = FakeEnv(tmp_path, scripts(), now=lambda: SUNDAY)
    assert pick_only(f.env()) == "weekend" and f.cmds == []


def test_each_stage_and_the_stop_go_to_the_ledger(tmp_path):
    _, f = full_item(tmp_path)
    entries = read_ledger(f.runtime)
    stages = [(e.branch, e.stage, e.model, e.outcome) for e in entries if isinstance(e, StageEntry)]
    b = "loop/row-a"
    assert stages == [
        ("", "probe", "haiku", "ok"),
        (b, "spec", "opus", "ok"),
        (b, "plan", "opus", "ok"),
        (b, "build", "sonnet", "more"),
        (b, "build", "sonnet", "ok"),
        (b, "pr", "sonnet", "ok"),
    ]
    assert isinstance(entries[-1], StopEntry) and entries[-1].reason == "done"


def test_a_crashed_run_records_a_crash_stop(tmp_path):
    f = FakeEnv(tmp_path, scripts())

    def boom(cmd):
        raise RuntimeError("x")

    env = replace(f.env(), sh=boom)
    with pytest.raises(RuntimeError):
        run(env)
    assert read_ledger(f.runtime)[-1].reason == "crash"


def test_a_park_decided_without_a_session_is_in_the_ledger(tmp_path):
    _, f = full_item(tmp_path, spec_text=GOOD_SPEC.replace("## Calls made for the owner", "## Other"))
    last = [e for e in read_ledger(f.runtime) if isinstance(e, StageEntry)][-1]
    assert (last.stage, last.outcome, last.cost) == ("pr", "park", None)
