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
    "scripts/feature_loop.py",
    "scripts/feature_loop.sh",
    "scripts/loop_prompts/build.md",
    "scripts/loop_prompts/pick.md",
    "scripts/loop_prompts/plan.md",
    "scripts/loop_prompts/pr.md",
    "scripts/loop_prompts/probe.md",
    "scripts/loop_prompts/spec.md",
    "tests/test_feature_loop.py",
)
OLD_LOOP_SCRIPT = "scripts/feature_loop.py"
NEW_ROADMAP = "docs/roadmap.md"
NEXT_STEPS = "docs/next-steps.md"
HOOK_SCRIPTS = ("test-layer-guard.mjs", "context-warn.mjs")
KNOWN_HASHES = Path(__file__).parent / "known_hashes.json"
PROSE_PATTERN = "implementer-haiku|implementer-sonnet|reviewer-sonnet|test-layer-guard|context-warn|token_report|feature_loop|loop_prompts"
ON_THE_KIT = ("kit:", "kit bench")
# git grep exits 1 when nothing matches; any other non-zero status is a real failure and still raises.
# -I skips binary files; docs/superpowers holds specs and plans, which name these files as history, not as live prose.
GREP_SCRIPT = (
    'git grep -n -I -E "$1" -- . ":(exclude).claude" ":(exclude)docs/superpowers"; status=$?; [ "$status" -le 1 ] || exit "$status"'
)


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
    hits = [parts for line in out.splitlines() if len(parts := line.split(":", 2)) == 3]
    return [f"{path}:{number}" for path, number, text in hits if not any(mark in text for mark in ON_THE_KIT)]


def prose_outside(hits: list[str], added: list[str]) -> list[str]:
    """Drop hits inside files this apply just added: the kit wrote that prose, the owner has nothing to edit."""
    return [hit for hit in hits if hit.rsplit(":", 1)[0] not in added]


def roadmap_files(repo: Path, run: Runner) -> list[str]:
    """Tracked old roadmap files to convert into docs/roadmap.md: `*roadmap*` under docs/, plus docs/next-steps.md."""
    tracked = run(["git", "ls-files", "docs"], repo).splitlines()
    old = {name for name in tracked if "roadmap" in Path(name).name or name == NEXT_STEPS}
    return sorted(old - {NEW_ROADMAP})


def loop_notes(had_loop: bool, agents: list[Path], has_loop_section: bool) -> list[str]:
    unload = [f"before merging, run scripts/feature_loop.sh uninstall in the repo (loaded: {agent.name})" for agent in agents]
    install = ["after merging, run kit loop install <repo>"] if had_loop else []
    section = ["add a loop section to .claude/kit.json (see the spec)"] if had_loop and not has_loop_section else []
    return [*unload, *install, *section]
