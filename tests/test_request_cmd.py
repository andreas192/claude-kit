"""UNIT: kit.request_cmd, filing a request on a target over temp git repos with a bare origin and a fake gh."""

import subprocess
from pathlib import Path
from unittest.mock import ANY

import pytest
from builders import commit, git

from kit.errors import KitError
from kit.gitrun import run
from kit.kitfile import Apply, KitFile, LoopConfig, write_kitfile
from kit.loop.requests import RequestRecord
from kit.request import parse_request
from kit.request_cmd import Filed, file_request, file_request_file, target_base
from kit.roadmap import parse_roadmap

REQ = "Target: investment\n### Fix FX rates\n- Status: open\n- Depends on: A\n\nRates are stale.\n"
ROADMAP = "## Now\n\n### A\n- Status: open\n"
PR_URL = "https://github.com/o/investment/pull/9"


def kit_file(version: str = "v0.4.0", loop: LoopConfig | None = None) -> KitFile:
    return KitFile("pytest", (Apply(version, "abc", "2026-10-28T00:00:00Z"),), loop)


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A bare origin, a target clone `investment/` with kit.json and a roadmap on main, and a requester beside it."""
    origin, target = tmp_path / "origin.git", tmp_path / "investment"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(target)], check=True, capture_output=True)
    for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        git(target, "config", key, value)
    write_kitfile(target, kit_file())
    commit(target, {"docs/roadmap.md": ROADMAP}, "init", "2026-10-28T10:00:00Z")
    git(target, "push", "-u", "origin", "main")
    git(target, "remote", "set-head", "origin", "-a")
    requester = tmp_path / "dividend-growth"
    requester.mkdir()
    return requester, target, origin


class GhFake:
    """Records gh calls, answers `gh pr list` and `gh pr create`; every other command runs for real."""

    def __init__(self, prs: str = "[]", fail_on: tuple[str, ...] = ()):
        self.prs, self.fail_on, self.calls = prs, fail_on, []

    def __call__(self, cmd: list[str], cwd: Path) -> str:
        if self.fail_on and tuple(cmd[: len(self.fail_on)]) == self.fail_on:
            raise KitError(f"{' '.join(cmd)} failed: refused")
        if cmd[0] != "gh":
            return run(cmd, cwd)
        self.calls.append(cmd)
        return self.prs if cmd[:3] == ["gh", "pr", "list"] else f"Creating pull request\n{PR_URL}\n"


def gh_fake(prs: str = "[]", fail_on: tuple[str, ...] = ()) -> GhFake:
    return GhFake(prs, fail_on)


def push_change(target: Path, files: dict[str, str]) -> None:
    commit(target, files, "change", "2026-10-28T11:00:00Z")
    git(target, "push")


def assert_no_request_left(target: Path, kit_home: Path) -> None:
    assert "request/" not in run(["git", "branch", "--list"], target)
    assert run(["git", "worktree", "list"], target).count("\n") == 1
    requests = kit_home / "requests"
    assert not requests.exists() or not any(requests.iterdir())


def test_file_request_pushes_one_roadmap_commit_and_opens_a_pr(pair, tmp_path):
    requester, target, origin = pair
    filed = file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh := gh_fake())
    assert filed == Filed("investment", "Fix FX rates", PR_URL)
    changed = run(["git", "diff", "--name-only", "main", "request/fix-fx-rates"], origin).split()
    assert changed == ["docs/roadmap.md"]
    roadmap = parse_roadmap(run(["git", "show", "request/fix-fx-rates:docs/roadmap.md"], origin))
    item = roadmap.by_title("Fix FX rates")
    assert (item.status, item.requested_by, item.section) == ("owner", "dividend-growth", "Requests")
    assert item.depends_on == ()
    create = next(c for c in gh.calls if c[:3] == ["gh", "pr", "create"])
    assert create[create.index("--base") + 1] == "main" and "request from dividend-growth: Fix FX rates" in create
    assert create[create.index("--head") + 1] == "request/fix-fx-rates"


def test_file_request_commit_message_names_the_requester(pair, tmp_path):
    requester, target, origin = pair
    file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())
    message = run(["git", "log", "-1", "--format=%B", "request/fix-fx-rates"], origin)
    assert message.startswith("roadmap: request from dividend-growth: Fix FX rates\n\nCo-Authored-By: ")


def test_file_request_body_names_the_loop_branch(pair, tmp_path):
    requester, target, _ = pair
    gh = gh_fake()
    file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh, loop_branch="loop/a")
    create = next(c for c in gh.calls if c[:3] == ["gh", "pr", "create"])
    assert "`loop/a`" in create[create.index("--body") + 1]


def test_file_request_leaves_the_target_checkout_and_kit_home_clean(pair, tmp_path):
    requester, target, _ = pair
    (target / "scratch.txt").write_text("owner's work")
    before = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], target)
    file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())
    assert run(["git", "rev-parse", "--abbrev-ref", "HEAD"], target) == before
    assert run(["git", "status", "--porcelain"], target).strip() == "?? scratch.txt"
    assert "request/" not in run(["git", "branch", "--list"], target)
    assert run(["git", "worktree", "list"], target).count("\n") == 1
    assert not any((tmp_path / "kit" / "requests").iterdir())


def test_a_failed_push_still_removes_worktree_and_branch(pair, tmp_path):
    requester, target, origin = pair
    with pytest.raises(KitError, match="git push .* failed: refused"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake(fail_on=("git", "push")))
    assert_no_request_left(target, tmp_path / "kit")
    assert "request/" not in run(["git", "branch", "--list"], origin)


def test_a_failed_pr_create_still_removes_worktree_and_branch(pair, tmp_path):
    requester, target, _ = pair
    with pytest.raises(KitError, match=r"^gh pr create --head request/fix-fx-rates failed: refused$"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake(fail_on=("gh", "pr", "create")))
    assert_no_request_left(target, tmp_path / "kit")


def test_a_failed_commit_has_a_one_line_error_and_cleans_up(pair, tmp_path):
    requester, target, _ = pair
    with pytest.raises(KitError, match=r"^git commit failed: refused$"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake(fail_on=("git", "commit")))
    assert_no_request_left(target, tmp_path / "kit")


def test_a_failed_worktree_add_keeps_its_own_error(pair, tmp_path):
    requester, target, _ = pair
    with pytest.raises(KitError, match="git worktree add .* failed: refused"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake(fail_on=("git", "worktree", "add")))
    assert_no_request_left(target, tmp_path / "kit")


def test_refuses_a_local_request_branch_it_did_not_create_and_keeps_it(pair, tmp_path):
    requester, target, _ = pair
    git(target, "branch", "request/fix-fx-rates")
    with pytest.raises(KitError, match="investment already has a local branch request/fix-fx-rates"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())
    assert "request/fix-fx-rates" in run(["git", "branch", "--list"], target)


def test_refuses_a_worktree_path_that_already_exists(pair, tmp_path):
    requester, target, _ = pair
    (tmp_path / "kit" / "requests" / "investment-fix-fx-rates").mkdir(parents=True)
    with pytest.raises(KitError, match="investment-fix-fx-rates already exists"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())
    assert "request/" not in run(["git", "branch", "--list"], target)


def test_refuses_a_title_already_on_the_base_roadmap(pair, tmp_path):
    requester, target, _ = pair
    with pytest.raises(KitError, match=r"already has 'A' \(line 3\)"):
        file_request(requester, target, parse_request("### A\n"), tmp_path / "kit", gh_fake())


def test_refuses_when_an_open_request_pr_exists(pair, tmp_path):
    requester, target, _ = pair
    gh = gh_fake(prs='[{"url": "https://x/pull/3"}]')
    with pytest.raises(KitError, match="https://x/pull/3"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh)
    listed = next(c for c in gh.calls if c[:3] == ["gh", "pr", "list"])
    assert listed[listed.index("--head") + 1] == "request/fix-fx-rates"
    assert listed[listed.index("--state") + 1] == "open"


def test_refuses_unreadable_gh_pr_list_output(pair, tmp_path):
    requester, target, _ = pair
    with pytest.raises(KitError, match="gh pr list"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake(prs="oops"))


def test_refuses_a_target_below_v0_4_0(pair, tmp_path):
    requester, target, _ = pair
    write_kitfile(target, kit_file("v0.3.0"))
    push_change(target, {})
    with pytest.raises(KitError, match="apply v0.4.0 or later to investment first"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())


def test_refuses_a_target_without_kit_json(pair, tmp_path):
    requester, target, _ = pair
    (target / ".claude" / "kit.json").unlink()
    with pytest.raises(KitError, match="investment has no .claude/kit.json"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())


def test_refuses_a_target_with_an_invalid_roadmap(pair, tmp_path):
    requester, target, _ = pair
    push_change(target, {"docs/roadmap.md": "## Now\n\n### A\n- Status: bogus\n"})
    with pytest.raises(KitError, match="investment has no valid docs/roadmap.md on origin/main: docs/roadmap.md:3"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())


def test_refuses_a_target_without_a_roadmap(pair, tmp_path):
    requester, target, _ = pair
    git(target, "rm", "-q", "docs/roadmap.md")
    git(target, "commit", "-m", "drop")
    git(target, "push")
    with pytest.raises(KitError, match="investment has no valid docs/roadmap.md on origin/main"):
        file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())


def test_target_base_prefers_the_loop_base_branch(pair):
    _, target, _ = pair
    git(target, "push", "origin", "main:develop")
    write_kitfile(target, kit_file(loop=LoopConfig("develop")))
    assert target_base(target, run) == "develop"


def test_target_base_falls_back_to_origin_head(pair):
    _, target, _ = pair
    assert target_base(target, run) == "main"


def test_target_base_without_origin_head(pair):
    _, target, _ = pair
    git(target, "remote", "set-head", "origin", "-d")
    with pytest.raises(KitError, match="investment has no origin/HEAD; run git remote set-head origin -a there"):
        target_base(target, run)


def test_file_request_file_files_the_request_and_records_the_url(pair, tmp_path):
    requester, _, _ = pair
    path = tmp_path / "r.md"
    path.write_text(REQ)
    record = file_request_file(requester, ("../investment",), tmp_path / "kit", gh_fake(), path, "loop/a")
    assert record == RequestRecord("investment", "Fix FX rates", url=PR_URL)


def test_file_request_file_turns_errors_into_a_record(pair, tmp_path):
    requester, _, _ = pair
    path = tmp_path / "r.md"
    path.write_text("Target: capital-trading\n### X\n")
    record = file_request_file(requester, ("../investment",), tmp_path / "kit", gh_fake(), path, "loop/a")
    assert record == RequestRecord("capital-trading", "X", error=ANY) and "not in requests.targets" in record.error


def test_file_request_file_with_an_unparsable_file_names_the_file(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("nothing\n")
    record = file_request_file(tmp_path, ("../investment",), tmp_path / "kit", gh_fake(), path, "")
    assert (record.title, record.url) == ("r.md", "") and "no ### item" in record.error


def test_file_request_file_with_a_missing_file_names_the_file(tmp_path):
    path = tmp_path / "gone.md"
    record = file_request_file(tmp_path, ("../investment",), tmp_path / "kit", gh_fake(), path, "")
    assert (record.title, record.url) == ("gone.md", "") and "gone.md" in record.error


def test_file_request_file_errors_are_one_line(pair, tmp_path):
    requester, target, _ = pair
    push_change(target, {"docs/roadmap.md": "## Now\n\n### A\n- Status: bogus\n\n### B\n- Status: bogus\n"})
    path = tmp_path / "r.md"
    path.write_text(REQ)
    record = file_request_file(requester, ("../investment",), tmp_path / "kit", gh_fake(), path, "")
    assert record.error and "\n" not in record.error
