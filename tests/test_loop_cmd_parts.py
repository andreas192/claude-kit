"""UNIT: the testable parts of kit.loop_cmd, over temp git repos with a bare origin."""

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from builders import GOOD, add_loop_package, commit, git, tag

from kit.errors import KitError
from kit.gitrun import run
from kit.kitfile import Apply, KitFile, LoopConfig, write_kitfile
from kit.loop.driver import Env
from kit.loop.state import Status, write_status
from kit.loop_cmd import (
    ensure_worktree,
    fetch_prs,
    handover_command,
    install,
    loop_path,
    origin_latest,
    pending_handover,
    program,
    read_extra,
    remote_loop_branches,
    require_loop,
    resume,
    runtime_dir,
    status_lines,
    uninstall,
    write_settings,
)

QUESTIONS_SPEC = "# Spec\n\n## Questions for the owner\n\n- Which basis?\n\n## Calls made for the owner\n\n- X. Rejected: Y.\n"
ANSWERED_SPEC = "# Spec\n\n## Questions for the owner\n\n## Calls made for the owner\n\n- X. Rejected: Y.\n"


def init_origin(tmp_path: Path) -> tuple[Path, Path]:
    """A bare origin and a clone with one commit on main (docs/roadmap.md and .claude/kit.json)."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(repo)], check=True, capture_output=True)
    for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        git(repo, "config", key, value)
    write_kitfile(repo, KitFile("pytest", (Apply("v0.2.0", "abc", "2026-10-20T00:00:00Z"),), LoopConfig("main")))
    commit(repo, {"docs/roadmap.md": GOOD}, "init", "2026-10-20T10:00:00Z")
    git(repo, "push", "-u", "origin", "main")
    return origin, repo


def loop_branch(repo: Path, key: str, spec: str, stage: str) -> Path:
    """Push loop/<key> with a status file at `stage` and a spec; returns the spec path (repo-relative)."""
    spec_path = f"docs/superpowers/specs/2026-10-20-{key}-design.md"
    git(repo, "checkout", "-b", f"loop/{key}")
    status = Status(key, "Row", stage, spec_path, f"docs/superpowers/plans/2026-10-20-{key}.md")
    (repo / ".loop").mkdir()
    write_status(repo / ".loop" / "status.json", status)
    commit(repo, {spec_path: spec}, "spec", "2026-10-20T11:00:00Z")
    git(repo, "push", "-u", "origin", f"loop/{key}")
    git(repo, "checkout", "main")
    return Path(spec_path)


def sh_in(cwd: Path):
    def sh(cmd: list[str]) -> str:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout

    return sh


def env_for(tmp_path: Path, repo: Path) -> Env:
    worktree = tmp_path / "wt"
    ensure_worktree(repo, worktree, "main", run)
    logs: list[str] = []
    return Env(
        claude=lambda stage, text: [], sh=sh_in(worktree), notify=logs.append, log=logs.append, worktree=worktree,
        runtime=tmp_path / "runtime", today="2026-10-20", now=lambda: datetime(2026, 10, 21, 10),
        config=LoopConfig("main"), test_command="pytest", repo_name="repo",
    )


def test_runtime_dir_is_per_repo_name(tmp_path):
    assert runtime_dir(tmp_path / "home", tmp_path / "work" / "demo") == tmp_path / "home" / "loop" / "demo"


def test_require_loop_returns_the_section():
    kit = KitFile("t", (), LoopConfig("main"))
    assert require_loop(kit, Path("/r")) == LoopConfig("main")


@pytest.mark.parametrize("kit", [None, KitFile("t", ())])
def test_require_loop_without_a_section_is_a_kit_error(kit):
    with pytest.raises(KitError, match=r"/r/.claude/kit.json has no loop section"):
        require_loop(kit, Path("/r"))


def test_program_runs_the_cli_module_without_a_project(tmp_path):
    cmd = program(tmp_path / "demo")
    assert cmd[0].endswith("uv")
    assert cmd[1:] == ["run", "--no-project", "python", "-m", "kit.cli", "loop", "run", str(tmp_path / "demo")]


def test_loop_path_dedupes_tool_dirs_and_ends_with_system_dirs():
    found = {"claude": "/a/claude", "gh": "/b/gh", "uv": "/a/uv", "git": "/usr/bin/git", "node": "/b/node"}
    assert loop_path(found.get) == "/a:/b:/usr/bin:/usr/bin:/bin"


def test_loop_path_names_the_missing_tool():
    with pytest.raises(KitError, match="gh not found on PATH"):
        loop_path({"claude": "/a/claude", "uv": "/a/uv", "git": "/a/git", "node": "/a/node"}.get)


def test_ensure_worktree_adds_a_detached_worktree_once(tmp_path):
    _, repo = init_origin(tmp_path)
    worktree = repo / ".claude" / "worktrees" / "feature-loop"
    ensure_worktree(repo, worktree, "main", run)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=worktree, capture_output=True, text=True).stdout
    assert head == subprocess.run(["git", "rev-parse", "origin/main"], cwd=repo, capture_output=True, text=True).stdout
    ensure_worktree(repo, worktree, "main", run)


def test_remote_loop_branches_lists_origin_loop_branches(tmp_path):
    _, repo = init_origin(tmp_path)
    loop_branch(repo, "row-a", ANSWERED_SPEC, "parked")
    git(repo, "fetch", "origin")
    assert remote_loop_branches(repo, run) == ["loop/row-a"]


def test_fetch_prs_reads_loop_prs():
    rows = [{"number": 1, "headRefName": "loop/a", "state": "OPEN", "createdAt": "t", "url": "u"},
            {"number": 2, "headRefName": "feat/b", "state": "OPEN", "createdAt": "t", "url": "v"}]
    prs, error = fetch_prs(Path("/r"), lambda cmd, cwd: json.dumps(rows))
    assert error == "" and [p.head for p in prs] == ["loop/a"]


def test_fetch_prs_when_gh_is_missing():
    def missing(cmd, cwd):
        raise FileNotFoundError(cmd[0])

    assert fetch_prs(Path("/r"), missing) == (None, "not found")


def test_fetch_prs_when_gh_fails_keeps_stderr_reason():
    def failing(cmd, cwd):
        raise KitError("gh pr list failed: not logged in")

    assert fetch_prs(Path("/r"), failing) == (None, "not logged in")


def test_fetch_prs_when_gh_prints_garbage():
    assert fetch_prs(Path("/r"), lambda cmd, cwd: "oops") == (None, "unreadable output")


def test_origin_latest_reads_kit_json_from_origin_base(tmp_path):
    _, repo = init_origin(tmp_path)
    assert origin_latest(repo, "main", run) == "v0.2.0"


def test_origin_latest_without_kit_json_on_origin(tmp_path):
    origin, repo = init_origin(tmp_path)
    git(repo, "rm", "-q", ".claude/kit.json")
    git(repo, "commit", "-m", "drop")
    git(repo, "push")
    with pytest.raises(KitError, match="no .claude/kit.json on origin/main"):
        origin_latest(repo, "main", run)


def test_origin_latest_with_malformed_json(tmp_path):
    _, repo = init_origin(tmp_path)
    commit(repo, {".claude/kit.json": "{oops"}, "break", "2026-10-21T10:00:00Z")
    git(repo, "push")
    with pytest.raises(KitError, match="origin/main:.claude/kit.json is not valid"):
        origin_latest(repo, "main", run)


def test_handover_command_runs_the_cli_module_with_the_flags(tmp_path):
    cmd = handover_command(tmp_path / "demo", tmp_path / "home", weekend_ok=True, pick_only=False)
    assert cmd[1:] == [
        "-m", "kit.cli", "loop", "run", str(tmp_path / "demo"), "--no-handover",
        "--kit-home", str(tmp_path / "home"), "--weekend-ok",
    ]


def test_resume_refuses_while_questions_are_open(tmp_path):
    _, repo = init_origin(tmp_path)
    spec = loop_branch(repo, "row-a", QUESTIONS_SPEC, "parked")
    env = env_for(tmp_path, repo)
    with pytest.raises(KitError, match=f"answer the questions in {spec} first"):
        resume(env, "row-a")


def test_resume_refuses_a_branch_that_is_not_parked(tmp_path):
    _, repo = init_origin(tmp_path)
    loop_branch(repo, "row-a", ANSWERED_SPEC, "build")
    env = env_for(tmp_path, repo)
    with pytest.raises(KitError, match="loop/row-a is at stage build, not parked"):
        resume(env, "row-a")


def test_resume_refuses_a_branch_without_a_status_file(tmp_path):
    _, repo = init_origin(tmp_path)
    git(repo, "branch", "loop/row-a")
    git(repo, "push", "origin", "loop/row-a")
    env = env_for(tmp_path, repo)
    with pytest.raises(KitError, match="loop/row-a has no .loop/status.json"):
        resume(env, "row-a")


def test_resume_refuses_while_the_loop_is_running(tmp_path):
    from kit.loop.driver import acquire_lock

    _, repo = init_origin(tmp_path)
    loop_branch(repo, "row-a", ANSWERED_SPEC, "parked")
    env = env_for(tmp_path, repo)
    held = acquire_lock(env.runtime / "lock")
    try:
        with pytest.raises(KitError, match="loop is running"):
            resume(env, "row-a")
    finally:
        held.close()


def test_resume_refuses_a_branch_checked_out_in_another_worktree(tmp_path):
    _, repo = init_origin(tmp_path)
    loop_branch(repo, "row-a", ANSWERED_SPEC, "parked")
    git(repo, "checkout", "loop/row-a")
    env = env_for(tmp_path, repo)
    with pytest.raises(KitError, match=f"loop/row-a is checked out in {repo.resolve()}"):
        resume(env, "row-a")


def test_resume_of_a_branch_checked_out_in_the_loop_worktree_is_not_refused(tmp_path):
    _, repo = init_origin(tmp_path)
    loop_branch(repo, "row-a", ANSWERED_SPEC, "parked")
    env = env_for(tmp_path, repo)
    git(env.worktree, "checkout", "loop/row-a")
    resume(env, "row-a")


def test_resume_of_a_key_with_no_branch_on_origin_is_a_kit_error(tmp_path):
    _, repo = init_origin(tmp_path)
    env = env_for(tmp_path, repo)
    with pytest.raises(KitError, match="no branch loop/typo on origin"):
        resume(env, "typo")


def test_resume_writes_stage_spec_commits_and_pushes(tmp_path):
    origin, repo = init_origin(tmp_path)
    loop_branch(repo, "row-a", ANSWERED_SPEC, "parked")
    env = env_for(tmp_path, repo)
    resume(env, "row-a")
    show = lambda ref: subprocess.run(["git", "show", ref], cwd=origin, capture_output=True, text=True).stdout
    assert json.loads(show("loop/row-a:.loop/status.json"))["stage"] == "spec"
    subject = subprocess.run(["git", "log", "-1", "--format=%s", "loop/row-a"], cwd=origin, capture_output=True, text=True)
    assert subject.stdout.strip() == "chore(loop): row-a resume at spec"


def finish_kit_repo(tmp_path: Path, version: str = "v0.2.0") -> Path:
    kit = tmp_path / "kit-repo"
    kit.mkdir()
    git(kit, "init", "-b", "main")
    add_loop_package(kit)
    tag(kit, version, plugin_version=version.removeprefix("v"))
    return kit


def stub_tools(tmp_path: Path) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("claude", "gh", "uv", "git", "node"):
        (bin_dir / name).write_text("")
    return {name: str(bin_dir / name) for name in ("claude", "gh", "uv", "git", "node")}


def installed(tmp_path: Path, launchctl=None) -> tuple[Path, Path, Path]:
    from kit.snapshot import snapshot

    _, repo = init_origin(tmp_path)
    home, agents = tmp_path / "home", tmp_path / "agents"
    snapshot(finish_kit_repo(tmp_path), "v0.2.0", home, run)
    plist = install(repo, home, agents, launchctl, stub_tools(tmp_path).get)
    return repo, home, plist


def test_install_writes_the_plist_pinned_to_the_snapshot_src(tmp_path):
    repo, home, plist = installed(tmp_path)
    text = plist.read_text()
    assert plist.name == "com.kit.loop.repo.plist"
    assert f"<key>PYTHONPATH</key><string>{home}/v0.2.0/src</string>" in text
    assert "<string>kit.cli</string>" in text and f"<string>{home}</string>" in text
    assert "<key>Weekday</key><integer>5</integer>" in text and "<key>Weekday</key><integer>6</integer>" not in text
    assert (home / "loop" / "repo").is_dir()


def test_install_loads_the_agent_for_its_own_label_only(tmp_path):
    calls: list[list[str]] = []
    installed(tmp_path, lambda cmd, cwd: calls.append(cmd) or "")
    assert [c[:2] for c in calls] == [["launchctl", "bootout"], ["launchctl", "bootstrap"]]
    assert calls[0][2].endswith("/com.kit.loop.repo") and calls[1][3].endswith("com.kit.loop.repo.plist")


def test_install_ignores_a_failing_bootout_but_not_a_failing_bootstrap(tmp_path):
    def flaky(cmd, cwd):
        raise KitError(f"{cmd[1]} failed: boom")

    with pytest.raises(KitError, match="bootstrap failed"):
        installed(tmp_path, flaky)


def test_install_refuses_while_another_agent_runs_a_loop_for_the_repo(tmp_path):
    from kit.snapshot import snapshot

    _, repo = init_origin(tmp_path)
    home, agents = tmp_path / "home", tmp_path / "agents"
    agents.mkdir()
    (agents / "com.dgi.feature-loop.plist").write_text(f"<string>{repo}</string>")
    snapshot(finish_kit_repo(tmp_path), "v0.2.0", home, run)
    with pytest.raises(KitError) as error:
        install(repo, home, agents, None, stub_tools(tmp_path).get)
    assert "com.dgi.feature-loop.plist" in str(error.value)
    assert "run its uninstall first (for dividend-growth: scripts/feature_loop.sh uninstall)" in str(error.value)
    assert not (agents / "com.kit.loop.repo.plist").exists()


def test_install_needs_the_snapshot_of_the_latest_applied_version(tmp_path):
    _, repo = init_origin(tmp_path)
    with pytest.raises(KitError, match="no snapshot src for v0.2.0"):
        install(repo, tmp_path / "home", tmp_path / "agents", None, stub_tools(tmp_path).get)


def test_install_needs_a_loop_section(tmp_path):
    _, repo = init_origin(tmp_path)
    write_kitfile(repo, KitFile("pytest", (Apply("v0.2.0", "abc", "t"),)))
    with pytest.raises(KitError, match="has no loop section"):
        install(repo, tmp_path / "home", tmp_path / "agents", None, stub_tools(tmp_path).get)


def test_install_needs_a_valid_roadmap(tmp_path):
    _, repo = init_origin(tmp_path)
    (repo / "docs" / "roadmap.md").write_text("### A\n- Status: nope\n")
    with pytest.raises(KitError, match=r"docs/roadmap.md:1"):
        install(repo, tmp_path / "home", tmp_path / "agents", None, stub_tools(tmp_path).get)


def test_pending_handover_returns_a_newer_installed_snapshot(tmp_path):
    _, repo = init_origin(tmp_path)
    home = tmp_path / "home"
    (home / "v0.2.0" / "src" / "kit").mkdir(parents=True)
    (home / "v0.2.0" / "src" / "kit" / "cli.py").write_text("")
    logs: list[str] = []
    assert pending_handover(repo, "main", home, "v0.1.0", run, logs.append) == home / "v0.2.0" / "src"
    assert pending_handover(repo, "main", home, "v0.2.0", run, logs.append) is None
    assert logs == []


def test_pending_handover_logs_a_failure_and_stays_on_this_version(tmp_path):
    _, repo = init_origin(tmp_path)
    commit(repo, {".claude/kit.json": "{oops"}, "break", "2026-10-21T10:00:00Z")
    git(repo, "push")
    logs: list[str] = []
    assert pending_handover(repo, "main", tmp_path / "home", "v0.1.0", run, logs.append) is None
    assert len(logs) == 1 and logs[0].startswith("handover skipped: ")


def test_pending_handover_logs_an_unparsable_version(tmp_path):
    _, repo = init_origin(tmp_path)
    write_kitfile(repo, KitFile("pytest", (Apply("main-ish", "abc", "t"),), LoopConfig("main")))
    commit(repo, {}, "odd version", "2026-10-21T10:00:00Z")
    git(repo, "push")
    logs: list[str] = []
    assert pending_handover(repo, "main", tmp_path / "home", "v0.1.0", run, logs.append) is None
    assert "not a release version" in logs[0]


def test_read_extra_is_empty_without_the_file_and_reads_it_otherwise(tmp_path):
    assert read_extra(tmp_path) == {}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "loop-settings.json").write_text('{"permissions": {"allow": ["Bash(x *)"]}}')
    assert read_extra(tmp_path) == {"permissions": {"allow": ["Bash(x *)"]}}


def test_read_extra_names_a_file_that_is_not_json(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "loop-settings.json").write_text("{oops")
    with pytest.raises(KitError, match="loop-settings.json is not valid JSON"):
        read_extra(tmp_path)


def test_write_settings_merges_extra_forbidden_paths_and_the_runtime(tmp_path):
    repo, runtime = tmp_path / "repo", tmp_path / "home" / "loop" / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "loop-settings.json").write_text('{"permissions": {"allow": ["Bash(uv run dgi *)"]}}')
    path = write_settings(repo, runtime, LoopConfig("main", forbidden_paths=("../investment",)), "uv run pytest -q")
    permissions = json.loads(path.read_text())["permissions"]
    assert path == runtime / "settings.json"
    assert "Bash(uv run dgi *)" in permissions["allow"] and "Bash(uv run pytest -q*)" in permissions["allow"]
    assert f"Write(/{runtime.resolve()}/**)" in permissions["allow"]
    assert f"Edit(/{(repo / '../investment').resolve()}/**)" in permissions["deny"]


def test_uninstall_boots_out_its_own_label_and_removes_the_plist(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "com.kit.loop.demo.plist").write_text("x")
    calls: list[list[str]] = []
    plist = uninstall(tmp_path / "demo", agents, lambda cmd, cwd: calls.append(cmd) or "")
    assert not plist.exists() and calls[0][:2] == ["launchctl", "bootout"] and calls[0][2].endswith("/com.kit.loop.demo")
    uninstall(tmp_path / "demo", agents, None)


def test_status_lines_are_launchd_state_then_the_last_log_lines(tmp_path):
    (tmp_path / "loop.log").write_text("\n".join(f"l{i}" for i in range(25)) + "\n")
    lines = status_lines(tmp_path / "demo", tmp_path, lambda cmd, cwd: "\n".join(f"p{i}" for i in range(40)))
    assert lines[:20] == [f"p{i}" for i in range(20)] and lines[20:] == [f"l{i}" for i in range(5, 25)]


def test_status_lines_say_when_the_agent_is_not_loaded_and_there_is_no_log(tmp_path):
    def not_loaded(cmd, cwd):
        raise KitError("launchctl print failed: Could not find service")

    lines = status_lines(tmp_path / "demo", tmp_path, not_loaded)
    assert lines[0].startswith("launchd: com.kit.loop.demo not loaded") and lines[1] == "no loop.log yet"
