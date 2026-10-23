"""UNIT: kit.status, the kit repos next to each other, and bench.run.default_control."""

from kit.bench.run import default_control
from kit.kitfile import Apply, KitFile, write_kitfile
from kit.status import RepoStatus, find_kit_repos, status_lines


def kit_repo(base, name, applies):
    (base / name).mkdir()
    write_kitfile(base / name, KitFile("pytest", tuple(applies)))
    return base / name


def test_find_kit_repos_reads_last_apply_of_repos_with_kit_json(tmp_path):
    kit_repo(tmp_path, "a", [Apply("v0.1.0", "c1", "t1"), Apply("v0.2.0", "c2", "t2", (".claude/agents/x.md",))])
    (tmp_path / "b").mkdir()
    (tmp_path / "file.txt").write_text("x")
    assert find_kit_repos(tmp_path) == [RepoStatus("a", "v0.2.0", (".claude/agents/x.md",))]


def test_find_kit_repos_sorted_by_name(tmp_path):
    kit_repo(tmp_path, "z", [Apply("v0.1.0", "c", "t")])
    kit_repo(tmp_path, "m", [Apply("v0.1.0", "c", "t")])
    assert [r.name for r in find_kit_repos(tmp_path)] == ["m", "z"]


def test_find_kit_repos_of_a_missing_base_is_empty(tmp_path):
    assert find_kit_repos(tmp_path / "nope") == []


def test_status_lines_show_version_and_overrides():
    lines = status_lines([RepoStatus("a", "v0.2.0", (".claude/agents/x.md",)), RepoStatus("b", "v0.1.0", ())])
    assert lines == ["a  v0.2.0  overrides: .claude/agents/x.md", "b  v0.1.0"]


def test_status_lines_say_so_when_nothing_is_found():
    assert status_lines([]) == ["no repos with .claude/kit.json found"]


def test_default_control_is_the_other_kit_repo(tmp_path):
    a = kit_repo(tmp_path, "a", [Apply("v0.1.0", "c", "t")])
    b = kit_repo(tmp_path, "b", [Apply("v0.1.0", "c", "t")])
    assert default_control(a) == b and default_control(b) == a


def test_default_control_is_none_for_the_only_repo(tmp_path):
    assert default_control(kit_repo(tmp_path, "a", [Apply("v0.1.0", "c", "t")])) is None
