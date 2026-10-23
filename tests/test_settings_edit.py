import copy
from pathlib import Path

import pytest

from kit.errors import KitError
from kit.settings_edit import read_settings, with_kit, with_permissions, without_hook_scripts, write_settings

GUARD = 'node "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.mjs"'


def _command(script):
    return {"type": "command", "command": f'node "$CLAUDE_PROJECT_DIR/.claude/hooks/{script}"'}


DGI_SETTINGS = {
    "enabledPlugins": {"ponytail@ponytail": True},
    "hooks": {
        "PreToolUse": [{"matcher": "Write|Edit", "hooks": [_command("test-layer-guard.mjs")]}],
        "Stop": [{"hooks": [_command("context-warn.mjs")]}],
        "UserPromptSubmit": [{"hooks": [_command("context-warn.mjs")]}],
    },
    "permissions": {"allow": ["Bash(grep *)", "Bash(git status *)", "Bash(git show *)"]},
}

INVEST_SETTINGS = {
    "enabledPlugins": {"ponytail@ponytail": True},
    "hooks": {
        "PreToolUse": [
            {"matcher": "Write|Edit", "hooks": [_command("test-layer-guard.mjs"), _command("guard.mjs")]},
            {"matcher": "Bash", "hooks": [_command("guard.mjs")]},
        ]
    },
}


def test_dgi_settings_lose_both_local_hooks_and_keep_the_rest():
    s, removed = without_hook_scripts(with_kit(DGI_SETTINGS, "v0.1.0", Path("/h/v0.1.0")), ["test-layer-guard.mjs", "context-warn.mjs"])
    assert "hooks" not in s and len(removed) == 3
    assert s["permissions"] == DGI_SETTINGS["permissions"] and s["enabledPlugins"]["ponytail@ponytail"] is True
    assert s["extraKnownMarketplaces"]["kit-v0-1-0"] == {"source": {"source": "directory", "path": "/h/v0.1.0"}}
    assert s["enabledPlugins"]["kit@kit-v0-1-0"] is True


def test_invest_keeps_its_guard_in_both_matchers():
    s, removed = without_hook_scripts(INVEST_SETTINGS, ["test-layer-guard.mjs", "context-warn.mjs"])
    commands = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert commands == [GUARD] * 2 and len(removed) == 1


def test_upgrade_replaces_the_old_version():
    s = with_kit(with_kit({}, "v0.1.0", Path("/h/v0.1.0")), "v0.2.0", Path("/h/v0.2.0"))
    assert list(s["extraKnownMarketplaces"]) == ["kit-v0-2-0"] and list(s["enabledPlugins"]) == ["kit@kit-v0-2-0"]


def test_upgrade_keeps_unrelated_marketplaces_and_plugins():
    base = {"extraKnownMarketplaces": {"other": {"source": {}}}, "enabledPlugins": {"ponytail@ponytail": True}}
    s = with_kit(with_kit(base, "v0.1.0", Path("/h/v0.1.0")), "v0.2.0", Path("/h/v0.2.0"))
    assert list(s["extraKnownMarketplaces"]) == ["other", "kit-v0-2-0"]
    assert list(s["enabledPlugins"]) == ["ponytail@ponytail", "kit@kit-v0-2-0"]


def test_inputs_are_not_mutated():
    before = copy.deepcopy(DGI_SETTINGS)
    with_kit(DGI_SETTINGS, "v0.1.0", Path("/h"))
    without_hook_scripts(DGI_SETTINGS, ["context-warn.mjs"])
    with_permissions({}, {"allow": ["x"]})
    assert DGI_SETTINGS == before


def test_permissions_added_only_when_absent():
    assert with_permissions({}, {"allow": ["x"]}) == {"permissions": {"allow": ["x"]}}
    assert with_permissions(DGI_SETTINGS, {"allow": ["x"]})["permissions"] == DGI_SETTINGS["permissions"]


def test_bad_json_names_the_file(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text("{")
    with pytest.raises(KitError, match="settings.json"):
        read_settings(tmp_path)


def test_missing_settings_read_as_empty(tmp_path):
    assert read_settings(tmp_path) == {}


def test_write_then_read_round_trips_with_indent_and_newline(tmp_path):
    write_settings(tmp_path, DGI_SETTINGS)
    text = (tmp_path / ".claude/settings.json").read_text()
    assert text.endswith("}\n") and text.startswith('{\n  "enabledPlugins"')
    assert read_settings(tmp_path) == DGI_SETTINGS
