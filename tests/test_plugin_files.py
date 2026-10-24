"""UNIT: the plugin's manifest, agents and hooks.json, and kit.frontmatter."""

import json
import re
import tomllib
from pathlib import Path

import pytest

from kit.errors import KitError
from kit.frontmatter import parse_frontmatter

PLUGIN = Path(__file__).parents[1] / "plugin"
PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"


def test_plugin_manifest_name_and_version() -> None:
    m = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert (m["name"], m["version"]) == ("kit", tomllib.loads(PYPROJECT.read_text())["project"]["version"])


def test_every_agent_has_routing_frontmatter() -> None:
    paths = list((PLUGIN / "agents").glob("*.md"))
    assert len(paths) == 3
    for path in paths:
        fm = parse_frontmatter(path.read_text())
        assert {"name", "description", "model", "effort", "tools"} <= fm.keys()
        assert "uv run pytest" not in path.read_text()
        assert "test_command" in path.read_text()


def test_hooks_json_points_at_existing_scripts() -> None:
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    assert set(hooks) == {"PreToolUse", "Stop", "UserPromptSubmit"}
    for group in [g for groups in hooks.values() for g in groups]:
        for h in group["hooks"]:
            script = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(hooks/[\w-]+\.mjs)", h["command"]).group(1)
            assert (PLUGIN / script).exists()


def test_parse_frontmatter_returns_key_value_pairs() -> None:
    assert parse_frontmatter("---\nname: a\ndescription: b: c\n---\nbody") == {"name": "a", "description": "b: c"}


def test_parse_frontmatter_without_header_raises() -> None:
    with pytest.raises(KitError):
        parse_frontmatter("no header")
