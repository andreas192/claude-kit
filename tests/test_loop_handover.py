"""UNIT: kit.loop.handover, which snapshot the loop should run from."""

import json

import pytest
from builders import commit, git, init_origin

from kit.errors import KitError
from kit.gitrun import run
from kit.loop.handover import handover_target, latest_applied, origin_latest, snapshot_src


def make_snapshot(home, version):
    (home / version / "src/kit").mkdir(parents=True)
    (home / version / "src/kit/cli.py").write_text("")


def kit_json(*versions):
    applies = [{"version": v, "commit": "abc", "applied_at": "2026-10-01T00:00:00Z"} for v in versions]
    return json.dumps({"test_command": "t", "applies": applies})


def test_snapshot_src_is_inside_the_version_folder(tmp_path):
    assert snapshot_src(tmp_path, "v0.3.0") == tmp_path / "v0.3.0" / "src"


def test_latest_applied_is_the_last_apply():
    assert latest_applied(kit_json("v0.1.0", "v0.2.0")) == "v0.2.0"


def test_latest_applied_is_none_without_applies():
    assert latest_applied(kit_json()) is None


def test_handover_only_to_a_newer_existing_snapshot(tmp_path):
    make_snapshot(tmp_path, "v0.3.0")
    assert handover_target("v0.3.0", "v0.2.0", tmp_path) == tmp_path / "v0.3.0/src"
    assert handover_target("v0.2.0", "v0.2.0", tmp_path) is None
    assert handover_target("v0.4.0", "v0.2.0", tmp_path) is None
    assert handover_target(None, "v0.2.0", tmp_path) is None


def test_no_handover_to_an_older_snapshot(tmp_path):
    make_snapshot(tmp_path, "v0.1.0")
    assert handover_target("v0.1.0", "v0.2.0", tmp_path) is None


def test_semver_not_string_order(tmp_path):
    make_snapshot(tmp_path, "v0.10.0")
    assert handover_target("v0.10.0", "v0.9.0", tmp_path) == tmp_path / "v0.10.0/src"


def test_origin_latest_reads_kit_json_from_origin_base(tmp_path):
    _, repo = init_origin(tmp_path)
    assert origin_latest(repo, "main", run) == "v0.2.0"


def test_origin_latest_without_kit_json_on_origin(tmp_path):
    origin, repo = init_origin(tmp_path)
    git(repo, "rm", "-q", ".claude/kit.json")
    git(repo, "commit", "-m", "drop")
    git(repo, "push")
    with pytest.raises(KitError, match="no .claude/kit.json on origin/main"):
        origin_latest(repo, "main", run)


def test_origin_latest_with_malformed_json(tmp_path):
    _, repo = init_origin(tmp_path)
    commit(repo, {".claude/kit.json": "{oops"}, "break", "2026-10-21T10:00:00Z")
    git(repo, "push")
    with pytest.raises(KitError, match="origin/main:.claude/kit.json is not valid"):
        origin_latest(repo, "main", run)
