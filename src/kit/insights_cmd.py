"""`kit insights`: wiring for run, install and uninstall of the weekly report."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import date
from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner, run
from kit.insights.advise import advisor_command, write_settings
from kit.insights.run import INSIGHTS_DIR, Advisor, run_insights
from kit.loop.schedule import plist_xml
from kit.loop_cmd import Which, _bootout, _load, loop_path

LABEL = "com.kit.insights"
MONDAY = 1
HOUR = 9
TOOLS = ("claude", "uv", "git")
ADVISOR_TIMEOUT = 1800


def insights_program(kit_repo: Path, base: Path, kit_home: Path, which: Which) -> list[str]:
    uv = which("uv")
    if uv is None:
        raise KitError("uv not found on PATH")
    return [uv, "run", "--project", str(kit_repo), "kit", "insights", "run", "--base", str(base), "--kit-home", str(kit_home), "--notify"]


def insights_plist(kit_repo: Path, base: Path, kit_home: Path, which: Which) -> str:
    program = insights_program(kit_repo, base, kit_home, which)
    log = kit_home / INSIGHTS_DIR / "launchd.log"
    return plist_xml(LABEL, program, {"PATH": loop_path(which, TOOLS, "kit insights install")}, kit_repo, log, [HOUR], [MONDAY])


def install(kit_repo: Path, base: Path, kit_home: Path, agents_dir: Path, launchctl: Runner | None, which: Which = shutil.which) -> Path:
    xml = insights_plist(kit_repo, base, kit_home, which)
    (kit_home / INSIGHTS_DIR).mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist = agents_dir / f"{LABEL}.plist"
    plist.write_text(xml)
    if launchctl is not None:
        _load(launchctl, kit_repo, LABEL, plist)
    return plist


def uninstall(kit_repo: Path, agents_dir: Path, launchctl: Runner | None) -> Path:
    if launchctl is not None:
        _bootout(launchctl, kit_repo, LABEL)
    plist = agents_dir / f"{LABEL}.plist"
    plist.unlink(missing_ok=True)
    return plist


def notify_command(path: Path) -> list[str]:
    script = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
    return ["osascript", "-e", script, "kit insights", f"report ready: {path}"]


def claude_advisor(kit_repo: Path, kit_home: Path) -> Advisor:
    settings = write_settings(kit_home / INSIGHTS_DIR)

    def advise(prompt: str) -> str:
        try:
            done = subprocess.run(advisor_command(prompt, settings), cwd=kit_repo, capture_output=True, text=True, timeout=ADVISOR_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as error:
            return f"not json: {error}"
        return done.stdout

    return advise


def _launchctl(args: argparse.Namespace) -> Runner | None:
    return None if args.no_launchctl else run


def run_command(args: argparse.Namespace) -> int:
    advisor = None if args.no_advise else claude_advisor(args.kit_repo, args.kit_home)
    path = run_insights(args.base, args.kit_home, args.root, date.today(), args.weeks, advisor, run)
    print(path.read_text(), end="")
    if args.notify:
        subprocess.run(notify_command(path), check=False)
    return 0


def install_command(args: argparse.Namespace) -> int:
    print(install(args.kit_repo, args.base.resolve(), args.kit_home, args.launch_agents, _launchctl(args)))
    return 0


def uninstall_command(args: argparse.Namespace) -> int:
    print(f"removed {uninstall(args.kit_repo, args.launch_agents, _launchctl(args))}")
    return 0


INSIGHTS_COMMANDS = {"run": run_command, "install": install_command, "uninstall": uninstall_command}


def insights_command(args: argparse.Namespace) -> int:
    return INSIGHTS_COMMANDS[args.insights_command](args)
