"""UNIT: plugin/hooks/kit-command-guard.mjs, run under node with a kit.json built in code."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parents[1] / "plugin" / "hooks" / "kit-command-guard.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
DEFAULT = "uv run --project ~/Projects/Personal/claude-kit kit"


def run(project: Path, command: str, stdin: str | None = None) -> dict:
    payload = stdin if stdin is not None else json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    done = subprocess.run(
        ["node", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": shutil.which("node").rsplit("/", 1)[0], "CLAUDE_PROJECT_DIR": str(project)},
    )
    return json.loads(done.stdout) if done.stdout else {}


def recorded(tmp_path: Path, command: str) -> Path:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "kit.json").write_text(json.dumps({"test_command": "t", "applies": [], "kit_command": command}))
    return tmp_path


@pytest.mark.parametrize(
    "command",
    ["kit roadmap .", "cd /r && kit request a b c", "git status; kit loop status .", "x | kit bench . --control y", "echo\n  kit status"],
)
def test_a_bare_kit_command_is_denied_with_the_recorded_command(tmp_path: Path, command: str) -> None:
    out = run(recorded(tmp_path, "uv run --project /k kit"), command)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "`uv run --project /k kit <command>`" in out["permissionDecisionReason"]


def test_without_a_recorded_command_the_default_is_named(tmp_path: Path) -> None:
    out = run(tmp_path, "kit roadmap .")["hookSpecificOutput"]
    assert f"`{DEFAULT} <command>`" in out["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "uv run --project ~/x kit roadmap .",
        "uv run --project /k kit loop status . && echo done",
        "grep -n 'kit roadmap' docs/command.md",
        "ls claude-kit roadmap",
        "kit frobnicate",
        "git log --oneline",
    ],
)
def test_other_commands_are_allowed(tmp_path: Path, command: str) -> None:
    assert run(tmp_path, command) == {}


def test_unreadable_input_allows(tmp_path: Path) -> None:
    assert run(tmp_path, "", stdin="not json") == {}
