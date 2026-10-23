import argparse
import sys

from kit import __version__
from kit.errors import KitError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kit")
    parser.add_argument("--version", action="version", version=f"kit {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="show the kit state of this machine")
    return parser


def dispatch(args: argparse.Namespace) -> int:
    return 0


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
