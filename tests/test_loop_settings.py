"""UNIT: kit.loop.settings, the generated permissions for unattended loop sessions."""

from kit.loop.settings import base_settings, loop_settings


def test_forbidden_paths_resolve_against_the_repo_not_the_worktree(tmp_path):
    repo = tmp_path / "dividend-growth"
    repo.mkdir()
    s = loop_settings(base_settings(), {}, repo, ("../investment",), "uv run pytest -q", tmp_path / "rt")
    inv = (tmp_path / "investment").resolve()
    assert f"Edit(/{inv}/**)" in s["permissions"]["deny"]
    assert f"Write(/{inv}/**)" in s["permissions"]["deny"]


def test_repo_extras_are_unioned_without_duplicates(tmp_path):
    extra = {
        "permissions": {"allow": ["Read", "Bash(uv run dgi *)"], "deny": ["Bash(gh api*)", "Bash(kubectl *)"]},
        "env": {"X": "1"},
    }
    s = loop_settings(base_settings(), extra, tmp_path, (), "uv run pytest -q", tmp_path / "rt")
    allow, deny = s["permissions"]["allow"], s["permissions"]["deny"]
    assert allow.count("Read") == 1
    assert "Bash(uv run dgi *)" in allow
    assert "Bash(uv run pytest -q*)" in allow
    assert f"Write(/{tmp_path / 'rt'}/**)" in allow
    assert deny.count("Bash(gh api*)") == 1
    assert "env" not in s


def test_base_denies_pushes_merges_and_installs():
    deny = base_settings()["permissions"]["deny"]
    assert {"Bash(git push*)", "Bash(gh pr merge*)", "Bash(pip *)", "Bash(uv tool *)"} <= set(deny)


def test_extra_rules_with_parent_paths_are_pinned_to_the_repo_not_the_worktree(tmp_path):
    repo = tmp_path / "dividend-growth"
    repo.mkdir()
    extra = {
        "permissions": {
            "allow": ["Edit(./**)", "Read(./../shared/**)"],
            "deny": ["Read(../investment/data/**)", "Bash(rm -rf ../x)", "Write(src/**)"],
        }
    }
    s = loop_settings(base_settings(), extra, repo, (), "uv run pytest -q", tmp_path / "rt")
    allow, deny = s["permissions"]["allow"], s["permissions"]["deny"]
    assert f"Read(/{tmp_path.resolve()}/investment/data/**)" in deny
    assert "Read(../investment/data/**)" not in deny
    assert f"Read(/{tmp_path.resolve()}/shared/**)" in allow
    assert "Edit(./**)" in allow and "Write(src/**)" in deny and "Bash(rm -rf ../x)" in deny
