"""Dev script: print the JSON map of migration CANDIDATES hashes found in the given repos (read-only).

Run from the kit repo: uv run python scripts/known_hashes.py ../dividend-growth ../investment > src/kit/known_hashes.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from kit.migrate import CANDIDATES, file_digest


def collect(repos: list[Path]) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for repo in repos:
        for name in CANDIDATES:
            if (repo / name).is_file():
                found.setdefault(name, set()).add(file_digest(repo / name))
    return {name: sorted(found[name]) for name in sorted(found)}


def main(argv: list[str]) -> None:
    print(json.dumps(collect([Path(a) for a in argv]), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
