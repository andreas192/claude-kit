"""UNIT: kit.starter, starter files read from a version tag and copied only where missing."""

import json
import subprocess
from pathlib import Path

import pytest
from builders import commit, git, tag

from kit.errors import KitError
from kit.gitrun import run
from kit.starter import copy_missing, ignore_bench_reports, read_starter


@pytest.fixture
def kit_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "kit-repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    files = {
        "starter/permissions.json": json.dumps({"allow": ["Bash(git status *)"]}),
        "starter/CLAUDE.md": "tagged skeleton\n",
        "starter/docs/token-strategy.md": "tagged strategy\n",
    }
    commit(repo, files, "release", "2026-10-01T10:00:00Z")
    tag(repo, "v0.1.0")
    commit(repo, {"starter/CLAUDE.md": "edited after the tag\n"}, "later", "2026-10-02T10:00:00Z")
    return repo


def test_starter_is_read_from_the_tag_not_the_working_tree(kit_repo: Path) -> None:
    starter = read_starter(kit_repo, "v0.1.0", run)
    assert starter.permissions == {"allow": ["Bash(git status *)"]}
    assert starter.files == {"CLAUDE.md": "tagged skeleton\n", "docs/token-strategy.md": "tagged strategy\n"}


def test_tag_without_permissions_is_refused(kit_repo: Path) -> None:
    git(kit_repo, "rm", "-q", "starter/permissions.json")
    git(kit_repo, "commit", "-m", "drop permissions")
    tag(kit_repo, "v0.2.0")
    with pytest.raises(KitError, match="v0.2.0.*permissions.json"):
        read_starter(kit_repo, "v0.2.0", run)


def test_unknown_tag_is_refused(kit_repo: Path) -> None:
    with pytest.raises(KitError):
        read_starter(kit_repo, "v9.9.9", run)


def test_copy_missing_writes_only_absent_targets_and_lists_them(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("mine\n")
    added = copy_missing(tmp_path, {"CLAUDE.md": "skeleton\n", "docs/token-strategy.md": "strategy\n"})
    assert added == ["docs/token-strategy.md"]
    assert (tmp_path / "CLAUDE.md").read_text() == "mine\n"
    assert (tmp_path / "docs/token-strategy.md").read_text() == "strategy\n"


def test_ignore_bench_reports_adds_a_gitignore_that_hides_reports_not_the_baseline(tmp_path: Path) -> None:
    git(tmp_path, "init", "-b", "main")
    assert ignore_bench_reports(tmp_path) == [".claude/kit-bench/.gitignore"]
    bench = tmp_path / ".claude" / "kit-bench"
    (bench / "2026-10-24.md").write_text("report\n")
    (bench / "baseline.json").write_text("{}\n")
    status = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert "2026-10-24.md" not in status and "baseline.json" in status


def test_ignore_bench_reports_keeps_an_existing_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "kit-bench").mkdir(parents=True)
    (tmp_path / ".claude" / "kit-bench" / ".gitignore").write_text("mine\n")
    assert ignore_bench_reports(tmp_path) == []
    assert (tmp_path / ".claude" / "kit-bench" / ".gitignore").read_text() == "mine\n"
