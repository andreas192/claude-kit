"""`kit loop`: wiring for run, install, uninstall, status and resume. The logic sits in the small functions here."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from kit import __version__
from kit.errors import KitError
from kit.gitrun import Runner, run
from kit.kitfile import KITFILE, KitFile, LoopConfig, read_kitfile
from kit.loop import driver
from kit.loop.handover import handover_target, latest_applied, snapshot_src
from kit.loop.prs import PR_FIELDS, Pr, loop_prs
from kit.loop.schedule import loop_label, other_loop_agents, plist_xml, run_hours
from kit.loop.settings import base_settings, loop_settings
from kit.loop.state import owner_questions, read_status, write_status
from kit.loop.stream import claude_command, failure_line, stream_lines
from kit.roadmap import read_roadmap

STAGE_TIMEOUT = 4 * 3600
STATUS_LOG_LINES = 20
LOOP_TOOLS = ("claude", "gh", "uv", "git", "node")
SYSTEM_PATH = "/usr/bin:/bin"
DEFAULT_AGENTS = Path.home() / "Library" / "LaunchAgents"
WORKTREE = Path(".claude") / "worktrees" / "feature-loop"
EXTRA_SETTINGS = Path(".claude") / "loop-settings.json"
OLD_AGENT_HINT = "run its uninstall first (for dividend-growth: scripts/feature_loop.sh uninstall)"

Which = Callable[[str], str | None]


def runtime_dir(kit_home: Path, repo: Path) -> Path:
    return kit_home / "loop" / repo.name


def scratch_dir(repo: Path, root: Path | None = None) -> Path:
    """Where loop sessions write files such as the PR body: `~/.claude` is protected in don't-ask mode, so not the runtime dir."""
    return (root or Path(tempfile.gettempdir())).resolve() / "kit-loop" / repo.name


def require_loop(kit: KitFile | None, repo: Path) -> LoopConfig:
    if kit is None or kit.loop is None:
        raise KitError(f"{repo / KITFILE} has no loop section")
    return kit.loop


def program(repo: Path, which: Which = shutil.which) -> list[str]:
    uv = which("uv")
    if uv is None:
        raise KitError("uv not found on PATH")
    return [uv, "run", "--no-project", "python", "-m", "kit.cli", "loop", "run", str(repo)]


def loop_path(which: Which, tools: tuple[str, ...] = LOOP_TOOLS, command: str = "kit loop install") -> str:
    dirs: list[str] = []
    for tool in tools:
        found = which(tool)
        if found is None:
            raise KitError(f"{tool} not found on PATH; install it before '{command}'")
        dirs.append(str(Path(found).parent))
    return ":".join([*dict.fromkeys(dirs), SYSTEM_PATH])


def ensure_worktree(repo: Path, worktree: Path, base_branch: str, runner: Runner) -> None:
    if not worktree.exists():
        runner(["git", "fetch", "origin"], repo)
        runner(["git", "worktree", "add", "--detach", str(worktree), f"origin/{base_branch}"], repo)


def remote_loop_branches(repo: Path, runner: Runner) -> list[str]:
    out = runner(["git", "branch", "-r", "--list", "origin/loop/*"], repo)
    return [line.strip().removeprefix("origin/") for line in out.splitlines() if line.strip()]


def _gh_reason(error: Exception) -> str:
    if isinstance(error, OSError):
        return "not found"
    if isinstance(error, KitError):
        return str(error).split(" failed: ", 1)[-1]
    return "unreadable output"


def fetch_prs(repo: Path, runner: Runner) -> tuple[list[Pr] | None, str]:
    """The loop PRs, or None with the short reason gh could not give them."""
    try:
        return loop_prs(runner(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json", PR_FIELDS], repo)), ""
    except (KitError, OSError, ValueError, KeyError, TypeError) as error:
        return None, _gh_reason(error)


def origin_latest(repo: Path, base_branch: str, runner: Runner) -> str:
    """The latest applied kit version in .claude/kit.json on origin/<base_branch>, after a fetch."""
    ref = f"origin/{base_branch}:{KITFILE.as_posix()}"
    runner(["git", "fetch", "origin"], repo)
    try:
        text = runner(["git", "show", ref], repo)
    except KitError as error:
        raise KitError(f"no {KITFILE.as_posix()} on origin/{base_branch}") from error
    try:
        latest = latest_applied(text)
    except (ValueError, KeyError, TypeError, AttributeError, KitError) as error:
        raise KitError(f"{ref} is not valid: {error}") from error
    if latest is None:
        raise KitError(f"{ref} has no applied version")
    return latest


def pending_handover(
    repo: Path, base_branch: str, kit_home: Path, running: str, runner: Runner, log: Callable[[str], None]
) -> Path | None:
    """The newer snapshot src to hand over to; a failure to find out is logged and the run stays on this version."""
    try:
        return handover_target(origin_latest(repo, base_branch, runner), running, kit_home)
    except KitError as error:
        log(f"handover skipped: {error}")
        return None


def handover_command(repo: Path, kit_home: Path, weekend_ok: bool, pick_only: bool) -> list[str]:
    flags = [flag for flag, on in (("--weekend-ok", weekend_ok), ("--pick-only", pick_only)) if on]
    return [sys.executable, "-m", "kit.cli", "loop", "run", str(repo), "--no-handover", "--kit-home", str(kit_home), *flags]


def read_extra(repo: Path) -> dict:
    path = repo / EXTRA_SETTINGS
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError as error:
        raise KitError(f"{path} is not valid JSON: {error}") from error


def write_settings(repo: Path, runtime: Path, scratch: Path, config: LoopConfig, test_command: str) -> Path:
    settings = loop_settings(base_settings(), read_extra(repo), repo, config.forbidden_paths, test_command, scratch.resolve())
    runtime.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    path = runtime / "settings.json"
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def _git_in(worktree: Path) -> Callable[[list[str]], str]:
    def sh(cmd: list[str]) -> str:
        return subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, check=True).stdout

    return sh


def _claude_in(worktree: Path, settings: Path) -> Callable[[str, str], list[str]]:
    def claude(stage: str, text: str) -> list[str]:
        try:
            done = subprocess.run(claude_command(stage, text, settings), cwd=worktree, capture_output=True, text=True, timeout=STAGE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return [failure_line(f"claude timed out after {STAGE_TIMEOUT // 3600} hours")]
        return stream_lines(done.stdout, done.returncode, done.stderr)

    return claude


def _notify_with(repo_name: str) -> Callable[[str], None]:
    def notify(msg: str) -> None:
        try:
            subprocess.run(driver.notify_command(msg, repo_name), check=False)
        except OSError:
            pass

    return notify


def file_log(runtime: Path) -> Callable[[str], None]:
    def log(msg: str) -> None:
        runtime.mkdir(parents=True, exist_ok=True)
        with (runtime / "loop.log").open("a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")

    return log


def real_env(repo: Path, runtime: Path, config: LoopConfig, test_command: str, weekend_ok: bool) -> driver.Env:
    worktree = repo / WORKTREE
    scratch = scratch_dir(repo)
    settings = write_settings(repo, runtime, scratch, config, test_command)
    return driver.Env(
        claude=_claude_in(worktree, settings),
        sh=_git_in(worktree),
        notify=_notify_with(repo.name),
        log=file_log(runtime),
        worktree=worktree,
        runtime=runtime,
        scratch=scratch,
        today=datetime.now().strftime("%Y-%m-%d"),
        now=datetime.now,
        config=config,
        test_command=test_command,
        repo_name=repo.name,
        weekend_ok=weekend_ok,
        kit_version=f"v{__version__}",
    )


def resume(env: driver.Env, key: str) -> None:
    """Hand a parked branch back to the loop: its status file goes to stage spec, committed and pushed."""
    lock = driver.acquire_lock(env.runtime / "lock")
    if lock is None:
        raise KitError("the loop is running; resume when it has stopped")
    try:
        _resume_locked(env, f"loop/{key}")
    finally:
        lock.close()


def _require_remote_branch(env: driver.Env, branch: str) -> None:
    try:
        env.sh(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"])
    except subprocess.CalledProcessError as error:
        raise KitError(f"no branch {branch} on origin") from error


def checked_out_elsewhere(porcelain: str, branch: str, worktree: Path) -> Path | None:
    """The first worktree other than `worktree` that has `branch` checked out, from `git worktree list --porcelain`."""
    for block in porcelain.strip().split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        path = Path(fields.get("worktree", ""))
        if fields.get("branch") == f"refs/heads/{branch}" and path.resolve() != worktree.resolve():
            return path
    return None


def _require_free_branch(env: driver.Env, branch: str) -> None:
    other = checked_out_elsewhere(env.sh(["git", "worktree", "list", "--porcelain"]), branch, env.worktree)
    if other is not None:
        raise KitError(f"{branch} is checked out in {other}; switch that checkout off it (or answer in a separate worktree) first")


def _resume_locked(env: driver.Env, branch: str) -> None:
    env.sh(["git", "fetch", "origin", "--prune"])
    _require_remote_branch(env, branch)
    _require_free_branch(env, branch)
    env.sh(["git", "reset", "--hard"])
    env.sh(["git", "clean", "-fd"])
    # Resets to origin and drops unpushed local commits; safe, because a parked branch is always pushed.
    env.sh(["git", "checkout", "-B", branch, f"origin/{branch}"])
    status_path = env.worktree / ".loop" / "status.json"
    status = read_status(status_path)
    if status is None:
        raise KitError(f"{branch} has no .loop/status.json")
    spec = env.worktree / status.spec
    if owner_questions(spec.read_text() if spec.exists() else ""):
        raise KitError(f"answer the questions in {status.spec} first")
    if status.stage != "parked":
        raise KitError(f"{branch} is at stage {status.stage}, not parked")
    status.stage = "spec"
    write_status(status_path, status)
    env.sh(["git", "add", ".loop/status.json"])
    env.sh(["git", "commit", "-m", f"chore(loop): {status.key} resume at spec\n\n{driver.CO_AUTHOR}"])
    env.sh(["git", "push", "-u", "origin", branch])


def _other_agents_error(others: list[Path]) -> KitError:
    return KitError("\n".join(f"{path} already runs a loop for this repo; {OLD_AGENT_HINT}" for path in others))


def snapshot_for_install(repo: Path, config: LoopConfig, kit_home: Path) -> Path:
    latest = origin_latest(repo, config.base_branch, run)
    src = snapshot_src(kit_home, latest)
    if not (src / "kit" / "cli.py").is_file():
        raise KitError(f"no snapshot src for {latest} in {kit_home}; run kit apply {repo} at that version first")
    return src


def install(repo: Path, kit_home: Path, agents_dir: Path, launchctl: Runner | None, which: Which = shutil.which) -> Path:
    config = require_loop(read_kitfile(repo), repo)
    read_roadmap(repo)
    label = loop_label(repo.name)
    others = other_loop_agents(agents_dir, repo, label)
    if others:
        raise _other_agents_error(others)
    src = snapshot_for_install(repo, config, kit_home)
    runtime = runtime_dir(kit_home, repo)
    cmd = [*program(repo, which), "--kit-home", str(kit_home)]
    env = {"PATH": loop_path(which), "PYTHONPATH": str(src)}
    runtime.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist = agents_dir / f"{label}.plist"
    plist.write_text(plist_xml(label, cmd, env, repo, runtime / "launchd.log", run_hours(config.interval_hours)))
    if launchctl is not None:
        _load(launchctl, repo, label, plist)
    return plist


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _bootout(launchctl: Runner, repo: Path, label: str) -> None:
    try:
        launchctl(["launchctl", "bootout", f"{_domain()}/{label}"], repo)
    except KitError:
        pass


def _load(launchctl: Runner, repo: Path, label: str, plist: Path) -> None:
    _bootout(launchctl, repo, label)
    launchctl(["launchctl", "bootstrap", _domain(), str(plist)], repo)


def uninstall(repo: Path, agents_dir: Path, launchctl: Runner | None) -> Path:
    label = loop_label(repo.name)
    if launchctl is not None:
        _bootout(launchctl, repo, label)
    plist = agents_dir / f"{label}.plist"
    plist.unlink(missing_ok=True)
    return plist


def status_lines(repo: Path, runtime: Path, launchctl: Runner | None) -> list[str]:
    lines: list[str] = []
    if launchctl is not None:
        label = loop_label(repo.name)
        try:
            lines += launchctl(["launchctl", "print", f"{_domain()}/{label}"], repo).splitlines()[:STATUS_LOG_LINES]
        except KitError as error:
            lines.append(f"launchd: {label} not loaded ({error})")
    log = runtime / "loop.log"
    return lines + (log.read_text().splitlines()[-STATUS_LOG_LINES:] if log.is_file() else ["no loop.log yet"])


def _launchctl(args: argparse.Namespace) -> Runner | None:
    return None if args.no_launchctl else run


def run_loop(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    kit = read_kitfile(repo)
    config = require_loop(kit, repo)
    runtime = runtime_dir(args.kit_home, repo)
    if not args.no_handover:
        src = pending_handover(repo, config.base_branch, args.kit_home, f"v{__version__}", run, file_log(runtime))
        if src is not None:
            cmd = handover_command(repo, args.kit_home, args.weekend_ok, args.pick_only)
            return subprocess.run(cmd, env={**os.environ, "PYTHONPATH": str(src)}).returncode
    lock = driver.acquire_lock(runtime / "lock")
    if lock is None:
        return 0
    env = real_env(repo, runtime, config, kit.test_command, args.weekend_ok)

    def action(e: driver.Env) -> str:
        ensure_worktree(repo, e.worktree, config.base_branch, run)
        return driver.pick_only(e) if args.pick_only else driver.run(e)

    return driver.guarded(env, action)


def install_loop(args: argparse.Namespace) -> int:
    print(install(args.repo.resolve(), args.kit_home, args.launch_agents, _launchctl(args)))
    return 0


def uninstall_loop(args: argparse.Namespace) -> int:
    print(f"removed {uninstall(args.repo.resolve(), args.launch_agents, _launchctl(args))}")
    return 0


def status_loop(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    print("\n".join(status_lines(repo, runtime_dir(args.kit_home, repo), _launchctl(args))))
    return 0


def resume_loop(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    kit = read_kitfile(repo)
    config = require_loop(kit, repo)
    env = real_env(repo, runtime_dir(args.kit_home, repo), config, kit.test_command, False)
    ensure_worktree(repo, env.worktree, config.base_branch, run)
    resume(env, args.key)
    print(f"loop/{args.key} is back at stage spec")
    return 0


LOOP_COMMANDS = {
    "run": run_loop,
    "install": install_loop,
    "uninstall": uninstall_loop,
    "status": status_loop,
    "resume": resume_loop,
}


def loop_command(args: argparse.Namespace) -> int:
    return LOOP_COMMANDS[args.loop_command](args)
