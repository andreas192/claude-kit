import argparse
import sys
from datetime import date
from pathlib import Path

from kit import __version__
from kit.bench.run import default_control, run_bench
from kit.errors import KitError
from kit.gitrun import run
from kit.status import find_kit_repos, status_lines

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
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
    return parser


def bench_command(args: argparse.Namespace) -> int:
    control = args.control or default_control(args.repo)
    path = run_bench(args.repo, control, args.root, date.today(), run, args.since)
    print(path.read_text(), end="")
    return 0


def status_command(args: argparse.Namespace) -> int:
    print("\n".join(status_lines(find_kit_repos(args.base))))
    return 0


COMMANDS = {"bench": bench_command, "status": status_command}


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
