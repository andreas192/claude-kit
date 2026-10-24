import argparse
import sys
from datetime import date
from pathlib import Path

from kit import __version__
from kit.apply import apply
from kit.bench.run import default_control, run_bench
from kit.detect import FLAGS, ask_with_default
from kit.errors import KitError
from kit.gitrun import run
from kit.loop.pick import pick
from kit.loop_cmd import DEFAULT_AGENTS, fetch_prs, loop_command, remote_loop_branches
from kit.migrate import load_known
from kit.roadmap import read_roadmap
from kit.roadmap_report import format_report
from kit.snapshot import latest_tag
from kit.status import find_kit_repos, status_lines
from kit.verify import check_line

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
KIT_HOME = Path.home() / ".claude" / "kit"
KIT_REPO = Path(__file__).parents[2]
DEFAULT_BASE = Path.home() / "Projects" / "Personal"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kit")
    parser.add_argument("--version", action="version", version=f"kit {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="show the kit state of this machine")
    status.add_argument("--base", type=Path, default=DEFAULT_BASE)
    bench = subparsers.add_parser("bench", help="measure sessions per kit version window")
    bench.add_argument("repo", type=Path)
    bench.add_argument("--control", type=Path)
    bench.add_argument("--since", default="")
    bench.add_argument("--root", type=Path, default=PROJECTS_ROOT)
    apply_parser = subparsers.add_parser("apply", help="put a kit version into a repo on a branch and open a PR")
    apply_parser.add_argument("repo", type=Path)
    apply_parser.add_argument("--version", dest="kit_version")
    for key, flag in FLAGS.items():
        apply_parser.add_argument(flag, dest=key)
    apply_parser.add_argument("--no-pr", action="store_true")
    apply_parser.add_argument("--kit-home", type=Path, default=KIT_HOME)
    apply_parser.add_argument("--known-hashes", type=Path)
    apply_parser.add_argument("--root", type=Path, default=PROJECTS_ROOT)
    roadmap = subparsers.add_parser("roadmap", help="validate docs/roadmap.md and show what the loop would pick")
    roadmap.add_argument("repo", type=Path)
    add_loop_parser(subparsers)
    return parser


def add_loop_parser(subparsers) -> None:
    loop = subparsers.add_parser("loop", help="run, install, uninstall, inspect or resume the feature loop of a repo")
    actions = loop.add_subparsers(dest="loop_command", required=True)
    for name in ("run", "install", "uninstall", "status", "resume"):
        action = actions.add_parser(name)
        action.add_argument("repo", type=Path)
        action.add_argument("--kit-home", type=Path, default=KIT_HOME)
        if name in ("install", "uninstall", "status"):
            action.add_argument("--no-launchctl", action="store_true")
        if name in ("install", "uninstall"):
            action.add_argument("--launch-agents", type=Path, default=DEFAULT_AGENTS)
        if name == "run":
            action.add_argument("--pick-only", action="store_true")
            action.add_argument("--weekend-ok", action="store_true")
            action.add_argument("--no-handover", action="store_true")
        if name == "resume":
            action.add_argument("key")


def apply_command(args: argparse.Namespace) -> int:
    version = args.kit_version or latest_tag(KIT_REPO, run)
    answers = {key: getattr(args, key) for key in FLAGS if getattr(args, key) is not None}
    ask = ask_with_default(input) if sys.stdin.isatty() else None
    result = apply(
        args.repo, version, KIT_REPO, args.kit_home, answers, ask, not args.no_pr, load_known(args.known_hashes), args.root, run
    )
    print("\n".join([f"branch {result.branch}", f"commit {result.commit}", *map(check_line, result.checks)]))
    print(f"PR {result.pr_url or 'not opened (--no-pr)'}")
    return 0


def bench_command(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    control = args.control.resolve() if args.control else default_control(repo)
    path = run_bench(repo, control, args.root, date.today(), run, args.since)
    print(path.read_text(), end="")
    return 0


def status_command(args: argparse.Namespace) -> int:
    print("\n".join(status_lines(find_kit_repos(args.base))))
    return 0


def roadmap_command(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    roadmap = read_roadmap(repo)
    prs, gh_error = fetch_prs(repo, run)
    result = pick(roadmap, remote_loop_branches(repo, run), prs) if prs is not None else None
    print(format_report(roadmap, result, prs, gh_error), end="")
    return 0


COMMANDS = {
    "apply": apply_command,
    "bench": bench_command,
    "loop": loop_command,
    "roadmap": roadmap_command,
    "status": status_command,
}


def dispatch(args: argparse.Namespace) -> int:
    return COMMANDS[args.command](args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        return dispatch(args)
    except KitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
