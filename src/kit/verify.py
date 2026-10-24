"""Post-apply checks: settings parse, plugin hooks decide as expected, agents are well formed, the repo's tests pass."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kit.errors import KitError
from kit.frontmatter import parse_frontmatter
from kit.gitrun import NOT_RUNNABLE, RunInput
from kit.settings_edit import read_settings

AGENT_KEYS = ("name", "description", "model", "tools")
CONTEXT_WARN_STEP = "80000"
PROBE_TEST = "test_kit_probe.py"
SCRATCH_PREFIX = ".tmp-verify-"


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def check_settings(repo: Path) -> Check:
    try:
        read_settings(repo)
    except KitError as error:
        return Check("settings", False, str(error))
    return Check("settings", True, "settings.json parses")


def _guard_output(plugin: Path, repo: Path, run_input: RunInput, file: Path, text: str) -> dict:
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(file), "content": text}}
    done = run_input(
        ["node", str(plugin / "hooks" / "test-layer-guard.mjs")], repo, json.dumps(payload), {"CLAUDE_PROJECT_DIR": str(repo)}
    )
    if done.returncode != 0:
        raise KitError(f"test-layer-guard exited {done.returncode}: {done.stderr.strip()}")
    return json.loads(done.stdout).get("hookSpecificOutput", {}) if done.stdout else {}


def check_guard(plugin: Path, repo: Path, layers: dict, run_input: RunInput) -> Check:
    probe = f"from {layers['package']}.{layers['wiring_modules'][0]} import x"
    probe_test = Path(layers["pipeline_test"]).parent / PROBE_TEST
    try:
        denied = _guard_output(plugin, repo, run_input, repo / probe_test, probe)
        pipeline = _guard_output(plugin, repo, run_input, repo / layers["pipeline_test"], probe)
    except (KitError, json.JSONDecodeError) as error:
        return Check("guard", False, str(error))
    if denied.get("permissionDecision") != "deny":
        return Check("guard", False, f"a wiring import in {probe_test} was not denied")
    if "additionalContext" not in pipeline:
        return Check("guard", False, f"{layers['pipeline_test']} did not get the pipeline-layer context")
    return Check("guard", True, "wiring imports denied in unit tests; pipeline test gets its contract")


def _context_transcript(tmp: Path, name: str, context: int) -> Path:
    usage = {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": context}
    record = {"type": "assistant", "isSidechain": False, "message": {"model": "claude-sonnet-5-5", "usage": usage}}
    path = tmp / name
    path.write_text(json.dumps(record) + "\n")
    return path


def _context_warn_run(plugin: Path, tmp: Path, run_input: RunInput, transcript: Path, session: str) -> subprocess.CompletedProcess[str]:
    payload = {"hook_event_name": "Stop", "transcript_path": str(transcript), "session_id": session}
    env = {"TMPDIR": str(tmp), "KIT_CONTEXT_WARN_STEP": CONTEXT_WARN_STEP, "CLAUDE_PROJECT_DIR": str(tmp)}
    return run_input(["node", str(plugin / "hooks" / "context-warn.mjs")], tmp, json.dumps(payload), env)


def check_context_warn(plugin: Path, tmp: Path, run_input: RunInput) -> Check:
    """Two probes: silent below the step, and a `systemMessage` above it (a hook that dies silently fails the second)."""
    tmp.mkdir(parents=True, exist_ok=True)
    probes = (("kit-verify-below", 1000), ("kit-verify-above", int(CONTEXT_WARN_STEP) + 1000))
    runs = [_context_warn_run(plugin, tmp, run_input, _context_transcript(tmp, f"{s}.jsonl", c), s) for s, c in probes]
    below, above = runs
    for done in runs:
        if done.returncode != 0:
            return Check("context-warn", False, f"context-warn exited {done.returncode}: {done.stderr.strip()}")
    if below.stdout.strip():
        return Check("context-warn", False, "context-warn warned on a transcript under the step")
    if "systemMessage" not in above.stdout:
        return Check("context-warn", False, "context-warn did not warn on a transcript above the step")
    return Check("context-warn", True, "silent below the step, warns above it")


def check_agents(plugin: Path) -> Check:
    problems: list[str] = []
    for path in sorted((plugin / "agents").glob("*.md")):
        try:
            pairs = parse_frontmatter(path.read_text())
        except KitError as error:
            problems.append(f"{path.name}: {error}")
            continue
        missing = [key for key in AGENT_KEYS if not pairs.get(key)]
        if missing:
            problems.append(f"{path.name}: missing {', '.join(missing)}")
    if problems:
        return Check("agents", False, "; ".join(problems))
    return Check("agents", True, "every agent has name, description, model and tools")


def check_tests(repo: Path, test_command: str, run_input: RunInput) -> Check:
    done = run_input(["sh", "-c", test_command], repo, "", {})
    if done.returncode != 0:
        reason = f" ({done.stderr.strip()})" if done.returncode == NOT_RUNNABLE and done.stderr.strip() else ""
        return Check("tests", False, f"{test_command} failed{reason}; this may predate the kit: run it on the default branch to compare")
    return Check("tests", True, f"{test_command} passed")


def run_checks(plugin: Path, repo: Path, layers: dict, test_command: str, tmp: Path, run_input: RunInput) -> list[Check]:
    """Run every check, in order, even after a failure; `tmp` is a scratch dir for the context-warn hook's state."""
    return [
        check_settings(repo),
        check_guard(plugin, repo, layers, run_input),
        check_context_warn(plugin, tmp, run_input),
        check_agents(plugin),
        check_tests(repo, test_command, run_input),
    ]


def verify(plugin: Path, repo: Path, layers: dict, test_command: str, kit_home: Path, run_input: RunInput) -> list[Check]:
    """run_checks with a scratch dir inside kit_home (apply writes only there and in the repo), removed afterwards."""
    kit_home.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=kit_home, prefix=SCRATCH_PREFIX))
    try:
        return run_checks(plugin, repo, layers, test_command, tmp, run_input)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_line(check: Check) -> str:
    return f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}"


def require_passing(checks: list[Check], branch: str) -> None:
    failed = [f"{c.name}: {c.detail}" for c in checks if not c.passed]
    if failed:
        raise KitError(f"checks failed: {'; '.join(failed)}; branch {branch} left for inspection; no PR")
