"""UNIT: plugin/hooks/context-warn.mjs, run under node on a transcript built in code."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parents[1] / "plugin" / "hooks" / "context-warn.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def assistant(read: int, sidechain: bool = False, model: str = "claude-opus-5-5") -> str:
    usage = {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": read}
    return json.dumps({"type": "assistant", "isSidechain": sidechain, "message": {"model": model, "usage": usage}})


def run(tmp_path: Path, lines: list[str], event: str = "Stop", session: str = "s1", step: int = 80_000) -> dict:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(lines) + "\n")
    payload = {"hook_event_name": event, "transcript_path": str(transcript), "session_id": f"{tmp_path.name}-{session}"}
    (tmp_path / "repo").mkdir(exist_ok=True)
    done = subprocess.run(
        ["node", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": shutil.which("node").rsplit("/", 1)[0],
            "TMPDIR": str(tmp_path),
            "KIT_CONTEXT_WARN_STEP": str(step),
            "CLAUDE_PROJECT_DIR": str(tmp_path / "repo"),
        },
    )
    return json.loads(done.stdout) if done.stdout else {}


def test_silent_below_the_step(tmp_path: Path) -> None:
    assert run(tmp_path, [assistant(70_000)]) == {}


def test_stop_warns_the_owner_once_per_step(tmp_path: Path) -> None:
    first = run(tmp_path, [assistant(85_000)])
    assert "85k" in first["systemMessage"]
    assert run(tmp_path, [assistant(90_000)]) == {}
    assert "170k" in run(tmp_path, [assistant(170_000)])["systemMessage"]


def test_prompt_submit_asks_claude_for_the_handoff_lines(tmp_path: Path) -> None:
    text = run(tmp_path, [assistant(100_000)], event="UserPromptSubmit")["hookSpecificOutput"]["additionalContext"]
    assert "Handoff: <file>" in text
    assert "After /clear, paste: continue from <file>, next: <step>" in text


def test_each_event_warns_once_per_step(tmp_path: Path) -> None:
    """Stop runs first after every turn; it must not use up Claude's warning."""
    assert "systemMessage" in run(tmp_path, [assistant(100_000)])
    assert "hookSpecificOutput" in run(tmp_path, [assistant(100_000)], event="UserPromptSubmit")
    assert run(tmp_path, [assistant(110_000)], event="UserPromptSubmit") == {}


def test_uses_the_last_main_window_call(tmp_path: Path) -> None:
    lines = [assistant(100_000), assistant(10_000), assistant(500_000, sidechain=True), assistant(900_000, model="<synthetic>"), "bad"]
    assert run(tmp_path, lines) == {}


def test_names_the_strategy_doc_only_if_the_repo_has_it(tmp_path: Path) -> None:
    def text() -> str:
        session = str(len(list(tmp_path.iterdir())))
        return run(tmp_path, [assistant(100_000)], event="UserPromptSubmit", session=session)["hookSpecificOutput"]["additionalContext"]

    assert "docs/token-strategy.md" not in text()
    (tmp_path / "repo" / "docs").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "token-strategy.md").write_text("x")
    assert "docs/token-strategy.md" in text()


def test_state_file_has_no_dgi_prefix(tmp_path: Path) -> None:
    run(tmp_path, [assistant(100_000)])
    assert [p.name for p in tmp_path.glob("kit-context-warn-*")] and not list(tmp_path.glob("dgi-*"))


def test_runs_through_a_symlinked_path(tmp_path: Path) -> None:
    link = tmp_path / "linked-hook.mjs"
    link.symlink_to(HOOK)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(assistant(100_000) + "\n")
    payload = {"hook_event_name": "Stop", "transcript_path": str(transcript), "session_id": f"{tmp_path.name}-link"}
    env = {"PATH": shutil.which("node").rsplit("/", 1)[0], "TMPDIR": str(tmp_path), "CLAUDE_PROJECT_DIR": str(tmp_path)}
    done = subprocess.run(["node", str(link)], input=json.dumps(payload), capture_output=True, text=True, check=True, env=env)
    assert "100k" in json.loads(done.stdout)["systemMessage"]
