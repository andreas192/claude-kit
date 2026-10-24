"""UNIT: kit.snapshot, immutable per-version plugin marketplaces exported from git tags."""

import json

import pytest

from builders import add_loop_package, commit, git, tag
from kit.errors import KitError
from kit.gitrun import run
from kit.snapshot import latest_tag, marketplace_name, snapshot, tag_has_loop, tree_digest

PLUGIN_JSON = json.dumps({"name": "kit", "version": "0.1.0"})


@pytest.fixture
def kit_repo(tmp_path):
    repo = tmp_path / "kit-repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    files = {"plugin/.claude-plugin/plugin.json": PLUGIN_JSON, "plugin/agents/a.md": "tagged agent"}
    commit(repo, files, "release", "2026-10-01T10:00:00Z")
    tag(repo, "v0.1.0")
    return repo


def leftovers(home):
    return [p.name for p in home.iterdir() if p.name != "v0.1.0"]


def test_marketplace_name():
    assert marketplace_name("v1.12.3") == "kit-v1-12-3"


@pytest.mark.parametrize("bad", ["1.2", "1.2.3", "v1.2", "v1.2.3-rc1", "v1.2.3\n", "latest"])
def test_marketplace_name_rejects_non_versions(bad):
    with pytest.raises(KitError):
        marketplace_name(bad)


def test_snapshot_writes_marketplace_and_plugin(kit_repo, tmp_path):
    path = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    m = json.loads((path / ".claude-plugin/marketplace.json").read_text())
    assert path == tmp_path / "home" / "v0.1.0"
    assert m == {
        "name": "kit-v0-1-0",
        "owner": {"name": "claude-kit"},
        "plugins": [{"name": "kit", "source": "./plugins/kit", "description": "claude-kit v0.1.0"}],
    }
    assert (path / "plugins/kit/agents/a.md").read_text() == "tagged agent"
    assert (path / "plugins/kit/.claude-plugin/plugin.json").exists()


def test_second_snapshot_is_a_no_op_and_ignores_the_working_tree(kit_repo, tmp_path):
    first = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    (kit_repo / "plugin/agents/a.md").write_text("edited, not tagged")
    assert snapshot(kit_repo, "v0.1.0", tmp_path / "home", run) == first
    assert "edited" not in (first / "plugins/kit/agents/a.md").read_text()
    assert leftovers(tmp_path / "home") == []


def test_changed_snapshot_is_refused_and_left_untouched(kit_repo, tmp_path):
    path = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    (path / "plugins/kit/agents/a.md").write_text("tampered")
    with pytest.raises(KitError, match="must never change"):
        snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    assert (path / "plugins/kit/agents/a.md").read_text() == "tampered"
    assert leftovers(tmp_path / "home") == []


def test_snapshot_with_an_extra_file_is_refused(kit_repo, tmp_path):
    path = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    (path / "plugins/kit/agents/extra.md").write_text("added")
    with pytest.raises(KitError, match="must never change"):
        snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)


def test_plugin_version_must_match_the_tag(kit_repo, tmp_path):
    tag(kit_repo, "v0.2.0")  # plugin.json still says 0.1.0
    with pytest.raises(KitError, match="0.1.0"):
        snapshot(kit_repo, "v0.2.0", tmp_path / "home", run)
    assert list((tmp_path / "home").iterdir()) == []


def test_unknown_tag_leaves_nothing_behind(kit_repo, tmp_path):
    with pytest.raises(KitError):
        snapshot(kit_repo, "v9.9.9", tmp_path / "home", run)
    assert list((tmp_path / "home").iterdir()) == []


def test_invalid_version_is_refused_before_touching_disk(kit_repo, tmp_path):
    with pytest.raises(KitError):
        snapshot(kit_repo, "main", tmp_path / "home", run)
    assert not (tmp_path / "home").exists()


def test_tag_without_plugin_folder_is_refused(kit_repo, tmp_path):
    commit(kit_repo, {"other.txt": "x"}, "drop plugin", "2026-10-02T10:00:00Z")
    git(kit_repo, "rm", "-r", "-q", "plugin")
    git(kit_repo, "commit", "-m", "no plugin")
    tag(kit_repo, "v0.3.0")
    with pytest.raises(KitError):
        snapshot(kit_repo, "v0.3.0", tmp_path / "home", run)
    assert list((tmp_path / "home").iterdir()) == []


def test_snapshot_of_a_tag_with_the_loop_holds_src(kit_repo, tmp_path):
    add_loop_package(kit_repo)
    tag(kit_repo, "v0.2.0", plugin_version="0.2.0")
    path = snapshot(kit_repo, "v0.2.0", tmp_path / "home", run)
    assert (path / "src/kit/loop/__init__.py").exists() and (path / "plugins/kit").is_dir()
    assert (path / "src/kit/cli.py").exists()


def test_snapshot_of_a_tag_without_the_loop_has_no_src(kit_repo, tmp_path):
    assert not (snapshot(kit_repo, "v0.1.0", tmp_path / "home", run) / "src").exists()


def test_src_holds_the_tag_and_ignores_the_working_tree(kit_repo, tmp_path):
    add_loop_package(kit_repo)
    tag(kit_repo, "v0.2.0", plugin_version="0.2.0")
    (kit_repo / "src/kit/cli.py").write_text("edited, not tagged")
    path = snapshot(kit_repo, "v0.2.0", tmp_path / "home", run)
    assert (path / "src/kit/cli.py").read_text() == ""
    assert leftovers(tmp_path / "home") == ["v0.2.0"]


def test_tag_has_loop_only_with_a_loop_folder(kit_repo):
    assert not tag_has_loop(kit_repo, "v0.1.0", run)
    add_loop_package(kit_repo)
    tag(kit_repo, "v0.2.0", plugin_version="0.2.0")
    assert tag_has_loop(kit_repo, "v0.2.0", run)


def test_latest_tag_is_semver_ordered(kit_repo):
    tag(kit_repo, "v0.10.0")
    tag(kit_repo, "v0.9.0")
    assert latest_tag(kit_repo, run) == "v0.10.0"


def test_latest_tag_ignores_tags_that_are_not_releases(kit_repo):
    tag(kit_repo, "v0.2.0-rc1")
    tag(kit_repo, "vnext")
    tag(kit_repo, "v9")
    assert latest_tag(kit_repo, run) == "v0.1.0"


def test_latest_tag_without_release_tags_is_an_error(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    commit(repo, {"a": "x"}, "init", "2026-10-01T10:00:00Z")
    with pytest.raises(KitError, match="no release tag"):
        latest_tag(repo, run)


def test_tree_digest_is_stable_and_covers_paths_and_bytes(tmp_path):
    a, b, c, d = (tmp_path / n for n in "abcd")
    for root, order in ((a, ("x", "y")), (b, ("y", "x"))):
        for name in order:
            (root / "dir").mkdir(parents=True, exist_ok=True)
            (root / "dir" / name).write_text(name)
    (c / "dir").mkdir(parents=True)
    (c / "dir" / "x").write_text("x")
    (c / "dir" / "y").write_text("changed")
    (d / "dir").mkdir(parents=True)
    (d / "dir" / "x").write_text("x")
    (d / "dir" / "z").write_text("y")  # same bytes as y, different name
    assert tree_digest(a) == tree_digest(b)
    assert tree_digest(a) != tree_digest(c)
    assert tree_digest(a) != tree_digest(d)
