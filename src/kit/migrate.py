"""Migration by known content: drop local copies the plugin now provides, keep anything edited."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from kit.gitrun import Runner

CANDIDATES = (
    ".claude/agents/implementer-haiku.md",
    ".claude/agents/implementer-sonnet.md",
    ".claude/agents/reviewer-sonnet.md",
    ".claude/hooks/test-layer-guard.mjs",
    ".claude/hooks/context-warn.mjs",
    "scripts/token_report.py",
    "tests/test_token_report.py",
    "tests/test_context_warn_hook.py",
)
HOOK_SCRIPTS = ("test-layer-guard.mjs", "context-warn.mjs")
KNOWN_HASHES = Path(__file__).parent / "known_hashes.json"
PROSE_PATTERN = "implementer-haiku|implementer-sonnet|reviewer-sonnet|test-layer-guard|context-warn|token_report"
ON_THE_KIT = ("kit:", "kit bench")
# git grep exits 1 when nothing matches; any other non-zero status is a real failure and still raises.
GREP_SCRIPT = 'git grep -n -E "$1" -- . ":(exclude).claude"; status=$?; [ "$status" -le 1 ] || exit "$status"'


@dataclass(frozen=True)
class Migration:
    remove: tuple[str, ...]
    overrides: tuple[str, ...]


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_known(path: Path | None = None) -> dict[str, list[str]]:
    return json.loads((path or KNOWN_HASHES).read_text())


def plan_migration(repo: Path, known: dict[str, list[str]]) -> Migration:
    present = [name for name in CANDIDATES if (repo / name).is_file()]
    remove = tuple(name for name in present if file_digest(repo / name) in known.get(name, ()))
    return Migration(remove, tuple(name for name in present if name not in remove))


def apply_migration(repo: Path, migration: Migration) -> None:
    for name in migration.remove:
        (repo / name).unlink()


def prose_mentions(repo: Path, run: Runner) -> list[str]:
    out = run(["sh", "-c", GREP_SCRIPT, "sh", PROSE_PATTERN], repo)
    hits = (line.split(":", 2) for line in out.splitlines())
    return [f"{path}:{number}" for path, number, text in hits if not any(mark in text for mark in ON_THE_KIT)]


def prose_outside(hits: list[str], added: list[str]) -> list[str]:
    """Drop hits inside files this apply just added: the kit wrote that prose, the owner has nothing to edit."""
    return [hit for hit in hits if hit.rsplit(":", 1)[0] not in added]
