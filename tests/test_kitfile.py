"""UNIT: kit.kitfile, the .claude/kit.json record of applied versions."""

import json

import pytest

from kit.errors import KitError
from kit.kitfile import Apply, KitFile, read_kitfile, with_apply, write_kitfile


def test_with_apply_appends_and_refuses_the_same_version():
    k = with_apply(KitFile("uv run pytest -q", ()), Apply("v0.1.0", "abc", "2026-10-18T10:00:00Z"))
    assert [a.version for a in k.applies] == ["v0.1.0"]
    with pytest.raises(KitError, match="already on v0.1.0"):
        with_apply(k, Apply("v0.1.0", "def", "2026-10-19T10:00:00Z"))


def test_with_apply_allows_an_upgrade_after_another_version():
    k = KitFile("t", (Apply("v0.1.0", "abc", "2026-10-18T10:00:00Z"),))
    assert [a.version for a in with_apply(k, Apply("v0.2.0", "def", "2026-10-19T10:00:00Z")).applies] == ["v0.1.0", "v0.2.0"]


def test_kitfile_round_trip(tmp_path):
    k = KitFile("t", (Apply("v0.1.0", "abc", "2026-10-18T10:00:00Z", ("x.md",)),))
    write_kitfile(tmp_path, k)
    assert read_kitfile(tmp_path) == k and read_kitfile(tmp_path / "none") is None


def test_written_text_is_searchable_by_git_pickaxe(tmp_path):
    write_kitfile(tmp_path, KitFile("t", (Apply("v0.1.0", "abc", "2026-10-18T10:00:00Z", ("x.md",)),)))
    text = (tmp_path / ".claude" / "kit.json").read_text()
    assert '"version": "v0.1.0"' in text and text.endswith("\n")
    assert list(json.loads(text)) == ["test_command", "applies"]
    assert list(json.loads(text)["applies"][0]) == ["version", "commit", "applied_at", "overrides"]
