from pathlib import Path

import pytest
from builders import commit, git, merge_branch

from kit.bench.gitlog import Merge, default_branch, followed_by_fix, history, merged_at, merges
from kit.gitrun import run
from kit.errors import KitError


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-b", "main")
    commit(tmp_path, {"README.md": "x"}, "init", "2026-09-30T10:00:00Z")
    return tmp_path


def test_run_raises_kit_error_with_first_stderr_line(tmp_path):
    with pytest.raises(KitError, match="failed"):
        run(["git", "log"], tmp_path)


def test_default_branch_falls_back_to_main(repo):
    assert default_branch(repo, run) == "main"


def test_default_branch_reads_origin_head():
    assert default_branch(Path("."), lambda cmd, cwd: "origin/develop\n") == "develop"


def test_merges_list_files_against_first_parent(repo):
    merge_branch(repo, "feat/a", {"a.py": "1"}, "Merge pull request #1 from x/feat/a", "2026-10-01T10:00:00Z")
    [m] = [m for m in merges(repo, "main", run) if m.subject.startswith("Merge")]
    assert m.files == {"a.py"}


def test_merges_are_oldest_first(repo):
    merge_branch(repo, "feat/a", {"a.py": "1"}, "Merge a", "2026-10-01T10:00:00Z")
    merge_branch(repo, "feat/b", {"b.py": "1"}, "Merge b", "2026-10-02T10:00:00Z")
    assert [m.subject for m in merges(repo, "main", run)] == ["init", "Merge a", "Merge b"]


def test_fix_within_window_on_same_file_counts():
    ms = [Merge("1", "2026-10-01T10:00:00Z", "feat a", frozenset({"a.py"})),
          Merge("2", "2026-10-05T10:00:00Z", "Merge pull request #2 from x/fix/a", frozenset({"a.py"})),
          Merge("3", "2026-10-20T10:00:00Z", "fix: b", frozenset({"a.py"}))]
    assert followed_by_fix(ms) == [True, False, False]


def test_fix_on_other_file_does_not_count():
    ms = [Merge("1", "2026-10-01T10:00:00Z", "feat a", frozenset({"a.py"})),
          Merge("2", "2026-10-02T10:00:00Z", "fix: b", frozenset({"b.py"}))]
    assert followed_by_fix(ms) == [False, False]


def test_merged_at_finds_the_merge_that_brought_the_entry(repo):
    merge_branch(repo, "chore/claude-kit-v0.1.0", {".claude/kit.json": '{"applies": [{"version": "v0.1.0"}]}'}, "Merge kit", "2026-10-02T09:00:00Z")
    assert merged_at(repo, "v0.1.0", "main", run) == "2026-10-02T09:00:00+00:00"
    assert merged_at(repo, "v0.2.0", "main", run) is None


def test_history_lists_the_default_branch_merges(repo):
    assert [m.subject for m in history(repo, run)] == ["init"]


def test_history_is_empty_without_git(tmp_path):
    assert history(tmp_path, run) == []
