"""UNIT: kit.starter, starter files read from a version tag and copied only where missing."""

import json
from pathlib import Path

import pytest
from builders import commit, git, tag

from kit.errors import KitError
from kit.gitrun import run
from kit.starter import copy_missing, read_starter


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
