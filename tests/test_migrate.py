"""UNIT: kit.migrate, removing local copies by known content and listing prose that names them."""

import hashlib

import pytest

from builders import commit, git
from kit.gitrun import run
from pathlib import Path

from kit.migrate import (
    CANDIDATES,
    Migration,
    apply_migration,
    load_known,
    loop_notes,
    plan_migration,
    prose_mentions,
    prose_outside,
    roadmap_files,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    return repo


def test_known_file_is_removed_and_edited_one_kept(tmp_path):
    write(tmp_path, ".claude/agents/implementer-haiku.md", "stock")
    write(tmp_path, ".claude/hooks/context-warn.mjs", "edited")
    known = {".claude/agents/implementer-haiku.md": [sha("stock")], ".claude/hooks/context-warn.mjs": [sha("stock")]}
    assert plan_migration(tmp_path, known) == Migration((".claude/agents/implementer-haiku.md",), (".claude/hooks/context-warn.mjs",))


def test_absent_candidates_are_neither_removed_nor_overrides(tmp_path):
    assert plan_migration(tmp_path, {}) == Migration((), ())


def test_apply_migration_deletes_only_the_remove_list(tmp_path):
    write(tmp_path, ".claude/agents/implementer-haiku.md", "stock")
    write(tmp_path, ".claude/hooks/context-warn.mjs", "edited")
    apply_migration(tmp_path, Migration((".claude/agents/implementer-haiku.md",), (".claude/hooks/context-warn.mjs",)))
    assert not (tmp_path / ".claude/agents/implementer-haiku.md").exists()
    assert (tmp_path / ".claude/hooks/context-warn.mjs").read_text() == "edited"


def test_prose_mentions_skip_lines_already_on_the_kit(git_repo):
    commit(git_repo, {"CLAUDE.md": "use implementer-haiku\nuse kit:implementer-haiku\n", ".claude/agents/x.md": "implementer-haiku"}, "c", "2026-10-01T10:00:00Z")
    assert prose_mentions(git_repo, run) == ["CLAUDE.md:1"]


def test_prose_mentions_skip_kit_bench_lines(git_repo):
    commit(git_repo, {"docs/a.md": "see token_report\nrun kit bench instead of token_report\n"}, "c", "2026-10-01T10:00:00Z")
    assert prose_mentions(git_repo, run) == ["docs/a.md:1"]


def test_prose_mentions_skip_binary_files(git_repo):
    commit(git_repo, {"docs/a.md": "see token_report\n"}, "c", "2026-10-01T10:00:00Z")
    (git_repo / "blob.bin").write_bytes(b"token_report\x00\x01")
    git(git_repo, "add", "blob.bin")
    git(git_repo, "commit", "-m", "binary")
    assert prose_mentions(git_repo, run) == ["docs/a.md:1"]


def test_prose_mentions_ignore_lines_that_are_not_path_number_text(tmp_path):
    out = "Binary file blob.bin matches\ndocs/a.md:2:see token_report\nweird:line\n"
    assert prose_mentions(tmp_path, lambda cmd, cwd: out) == ["docs/a.md:2"]


def test_prose_mentions_skip_the_kit_own_specs_and_plans(git_repo):
    files = {"docs/superpowers/plans/p.md": "token_report\n", "docs/superpowers/specs/s.md": "token_report\n", "docs/b.md": "token_report\n"}
    commit(git_repo, files, "c", "2026-10-01T10:00:00Z")
    assert prose_mentions(git_repo, run) == ["docs/b.md:1"]


def test_prose_mentions_none_is_an_empty_list(git_repo):
    commit(git_repo, {"README.md": "nothing here\n"}, "c", "2026-10-01T10:00:00Z")
    assert prose_mentions(git_repo, run) == []


def test_prose_mentions_real_git_failure_is_not_swallowed(tmp_path):
    from kit.errors import KitError

    with pytest.raises(KitError):
        prose_mentions(tmp_path, run)


def test_packaged_known_hashes_cover_dividend_growth_files():
    known = load_known()
    assert all(known.get(p) for p in CANDIDATES)


def test_prose_outside_drops_hits_in_files_this_apply_added():
    hits = ["CLAUDE.md:3", "docs/token-strategy.md:54", "docs/token-strategy.md.bak:1"]
    assert prose_outside(hits, ["docs/token-strategy.md"]) == ["CLAUDE.md:3", "docs/token-strategy.md.bak:1"]


LOOP_FILES = (
    "scripts/feature_loop.py",
    "scripts/feature_loop.sh",
    *(f"scripts/loop_prompts/{name}.md" for name in ("build", "pick", "plan", "pr", "probe", "spec")),
    "tests/test_feature_loop.py",
)


def test_the_old_loop_files_are_candidates():
    assert set(LOOP_FILES) <= set(CANDIDATES)


def test_the_old_loop_files_with_known_hashes_are_removed(tmp_path):
    for name in LOOP_FILES:
        write(tmp_path, name, f"old {name}")
    known = {name: [sha(f"old {name}")] for name in LOOP_FILES}
    assert plan_migration(tmp_path, known) == Migration(tuple(n for n in CANDIDATES if n in LOOP_FILES), ())


def test_an_edited_feature_loop_is_kept_as_an_override(tmp_path):
    write(tmp_path, "scripts/feature_loop.py", "edited")
    write(tmp_path, "scripts/feature_loop.sh", "stock")
    known = {"scripts/feature_loop.py": [sha("stock")], "scripts/feature_loop.sh": [sha("stock")]}
    assert plan_migration(tmp_path, known) == Migration(("scripts/feature_loop.sh",), ("scripts/feature_loop.py",))


def test_prose_mentions_name_the_old_loop(git_repo):
    commit(git_repo, {"docs/a.md": "run feature_loop.sh\nsee loop_prompts/pick.md\n"}, "c", "2026-10-01T10:00:00Z")
    assert prose_mentions(git_repo, run) == ["docs/a.md:1", "docs/a.md:2"]


def test_roadmap_files_lists_old_roadmaps_but_not_the_new_one(git_repo):
    files = {
        "docs/superpowers/specs/2026-10-05-dgi-roadmap.md": "x",
        "docs/next-steps.md": "x",
        "docs/roadmap.md": "x",
        "docs/other.md": "x",
        "README.md": "x",
    }
    commit(git_repo, files, "c", "2026-10-01T10:00:00Z")
    assert roadmap_files(git_repo, run) == ["docs/next-steps.md", "docs/superpowers/specs/2026-10-05-dgi-roadmap.md"]


def test_roadmap_files_is_empty_without_any(git_repo):
    commit(git_repo, {"docs/roadmap.md": "x"}, "c", "2026-10-01T10:00:00Z")
    assert roadmap_files(git_repo, run) == []


def test_loop_notes_come_in_the_stated_order():
    agents = [Path("/a/com.old.one.plist"), Path("/a/com.old.two.plist")]
    assert loop_notes(True, agents, False, Path("/r/app")) == [
        "before merging, run scripts/feature_loop.sh uninstall in the repo (loaded: com.old.one.plist)",
        "before merging, run scripts/feature_loop.sh uninstall in the repo (loaded: com.old.two.plist)",
        "after merging, run kit loop install /r/app",
        "add a loop section to .claude/kit.json (see the spec)",
    ]


def test_loop_notes_are_empty_for_a_repo_without_a_loop():
    assert loop_notes(False, [], False, Path("/r/app")) == []


def test_loop_notes_skip_the_section_hint_when_the_section_exists():
    assert loop_notes(True, [], True, Path("/r/app")) == ["after merging, run kit loop install /r/app"]
