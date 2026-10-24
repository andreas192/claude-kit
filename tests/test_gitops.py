"""UNIT: kit.gitops, the git and gh calls `apply` makes on the target repo."""

import subprocess
from pathlib import Path

import pytest
from builders import commit, git

from kit.errors import KitError
from kit.gitops import commit_all, commit_time, create_branch, is_clean, open_pr, pr_body, retry_hint, retry_hint_on_failure
from kit.gitrun import run
from kit.migrate import Migration
from kit.verify import Check


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "t")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "commit.gpgsign", "false")
    commit(path, {"a.txt": "1"}, "first", "2026-10-01T10:00:00Z")
    return path


def test_is_clean_true_then_false_for_an_untracked_file(repo: Path) -> None:
    assert is_clean(repo, run)
    (repo / "new.txt").write_text("x")
    assert not is_clean(repo, run)


def test_is_clean_false_for_a_modified_tracked_file(repo: Path) -> None:
    (repo / "a.txt").write_text("2")
    assert not is_clean(repo, run)


def test_create_branch_switches_to_it(repo: Path) -> None:
    create_branch(repo, "chore/claude-kit-v0.1.0", run)
    assert run(["git", "branch", "--show-current"], repo).strip() == "chore/claude-kit-v0.1.0"


def test_commit_all_commits_new_files_and_returns_the_full_sha(repo: Path) -> None:
    (repo / "new.txt").write_text("x")
    sha = commit_all(repo, "feat: add", run)
    assert len(sha) == 40 and sha == run(["git", "rev-parse", "HEAD"], repo).strip()
    assert is_clean(repo, run)


def test_commit_time_is_utc_iso(repo: Path) -> None:
    sha = run(["git", "rev-parse", "HEAD"], repo).strip()
    assert commit_time(repo, sha, run) == "2026-10-01T10:00:00Z"


class Recorder:
    def __init__(self, out: str) -> None:
        self.out, self.calls = out, []

    def __call__(self, cmd: list[str], cwd: Path) -> str:
        self.calls.append(cmd)
        return self.out


def test_open_pr_pushes_the_branch_then_returns_the_url_line(tmp_path: Path) -> None:
    recorder = Recorder("Creating pull request\nhttps://github.com/o/r/pull/7\n")
    assert open_pr(tmp_path, "chore/x", "title", "body", recorder) == "https://github.com/o/r/pull/7"
    assert recorder.calls == [
        ["git", "push", "-u", "origin", "HEAD"],
        ["gh", "pr", "create", "--title", "title", "--body", "body"],
    ]


def failing_gh(cmd: list[str], cwd: Path) -> str:
    if cmd[0] == "gh":
        raise KitError("gh pr create failed: not logged in")
    return ""


def test_open_pr_failure_after_the_push_names_the_pushed_branch(tmp_path: Path) -> None:
    with pytest.raises(KitError, match=r"gh pr create failed: not logged in; pushed chore/x; run gh pr create by hand"):
        open_pr(tmp_path, "chore/x", "title", "body", failing_gh)


def test_open_pr_with_empty_gh_output_is_an_error_naming_the_branch(tmp_path: Path) -> None:
    with pytest.raises(KitError, match="no URL.*pushed chore/x"):
        open_pr(tmp_path, "chore/x", "title", "body", Recorder(""))


def test_open_pr_push_failure_is_not_reworded(tmp_path: Path) -> None:
    def failing_push(cmd: list[str], cwd: Path) -> str:
        raise KitError("git push failed: no remote")

    with pytest.raises(KitError) as raised:
        open_pr(tmp_path, "chore/x", "title", "body", failing_push)
    assert str(raised.value) == "git push failed: no remote"


def test_retry_hint_undoes_a_failed_apply(repo: Path) -> None:
    create_branch(repo, "chore/x", run)
    (repo / "a.txt").write_text("changed")
    (repo / "new.txt").write_text("x")
    (repo / ".claude").mkdir()
    (repo / ".claude" / "kit.json").write_text("{}")
    subprocess.run(["sh", "-c", retry_hint("chore/x").removeprefix("to retry: ")], cwd=repo, check=True, capture_output=True)
    assert run(["git", "branch", "--show-current"], repo).strip() == "main"
    assert run(["git", "branch", "--list", "chore/x"], repo).strip() == ""
    assert is_clean(repo, run) and not (repo / "new.txt").exists() and (repo / "a.txt").read_text() == "1"


def test_retry_hint_on_failure_appends_the_hint_to_a_kit_error() -> None:
    with pytest.raises(KitError, match="boom; to retry: .*git branch -D chore/x"):
        with retry_hint_on_failure("chore/x"):
            raise KitError("boom")


def test_retry_hint_on_failure_leaves_other_errors_and_success_alone() -> None:
    with retry_hint_on_failure("chore/x"):
        pass
    with pytest.raises(ValueError):
        with retry_hint_on_failure("chore/x"):
            raise ValueError("x")


def test_pr_body_lists_each_section_with_its_lines() -> None:
    body = pr_body(
        "v0.1.0",
        Migration(("scripts/token_report.py",), (".claude/agents/reviewer-sonnet.md",)),
        ["node .claude/hooks/context-warn.mjs"],
        ["docs/token-strategy.md"],
        ["CLAUDE.md:12"],
        [Check("settings", True, "settings.json parses"), Check("tests", False, "boom")],
    )
    sections = {s.splitlines()[0]: s.splitlines()[1:] for s in body.split("### ")[1:]}
    assert sections["Added"] == ["- docs/token-strategy.md", ""]
    assert "- scripts/token_report.py" in sections["Removed (known kit content)"]
    assert "- hook entry: node .claude/hooks/context-warn.mjs" in sections["Removed (known kit content)"]
    assert "- .claude/agents/reviewer-sonnet.md" in sections["Kept as local overrides"]
    assert "- CLAUDE.md:12" in sections["Edit by hand on this branch"]
    assert "- PASS settings: settings.json parses" in sections["Checks"]
    assert "- FAIL tests: boom" in sections["Checks"]


def test_pr_body_says_none_for_an_empty_section() -> None:
    body = pr_body("v0.1.0", Migration((), ()), [], [], [], [])
    assert body.count("- none") == 5
