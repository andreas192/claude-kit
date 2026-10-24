"""UNIT: kit.verify, the post-apply checks; hooks run under real node, the repo's test command under sh."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kit.errors import KitError
from kit.gitrun import run_input
from kit.verify import (
    Check,
    check_agents,
    check_context_warn,
    check_guard,
    check_line,
    check_settings,
    check_tests,
    require_passing,
    run_checks,
    verify,
)

PLUGIN = Path(__file__).parents[1] / "plugin"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
LAYERS = {
    "pipeline_test": "tests/test_cli_pipeline.py",
    "package": "dgi",
    "wiring_modules": ["cli", "pipeline"],
    "wiring_functions": ["run_refresh"],
    "conventions_doc": "docs/code-conventions.md",
}


def repo_with(tmp_path: Path, layers: dict) -> Path:
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "test-layers.json").write_text(json.dumps(layers))
    return repo


def test_settings_pass_when_absent_or_valid_and_fail_on_bad_json(tmp_path: Path) -> None:
    assert check_settings(tmp_path).passed
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    assert check_settings(tmp_path).passed
    (tmp_path / ".claude" / "settings.json").write_text("{nope")
    failed = check_settings(tmp_path)
    assert not failed.passed and "not valid JSON" in failed.detail


@needs_node
def test_guard_passes_with_the_repos_own_layers(tmp_path: Path) -> None:
    check = check_guard(PLUGIN, repo_with(tmp_path, LAYERS), LAYERS, run_input)
    assert check.passed, check.detail


@needs_node
def test_guard_probes_beside_a_nested_pipeline_test(tmp_path: Path) -> None:
    nested = {**LAYERS, "pipeline_test": "tests/e2e/test_cli_pipeline.py"}
    check = check_guard(PLUGIN, repo_with(tmp_path, nested), nested, run_input)
    assert check.passed, check.detail


@needs_node
def test_guard_fails_when_the_layers_target_another_package(tmp_path: Path) -> None:
    written = {**LAYERS, "package": "other", "wiring_modules": ["web"]}
    check = check_guard(PLUGIN, repo_with(tmp_path, written), LAYERS, run_input)
    assert not check.passed and "not denied" in check.detail


@needs_node
def test_guard_does_not_create_probe_files(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, LAYERS)
    check_guard(PLUGIN, repo, LAYERS, run_input)
    assert not (repo / "tests").exists()


@needs_node
def test_context_warn_passes_on_a_small_transcript(tmp_path: Path) -> None:
    check = check_context_warn(PLUGIN, tmp_path, run_input)
    assert check.passed, check.detail


@needs_node
def test_context_warn_fails_when_the_hook_cannot_run(tmp_path: Path) -> None:
    broken = tmp_path / "plugin"
    (broken / "hooks").mkdir(parents=True)
    (broken / "hooks" / "context-warn.mjs").write_text("process.exit(2)\n")
    check = check_context_warn(broken, tmp_path / "state", run_input)
    assert not check.passed and "exited 2" in check.detail


@needs_node
def test_context_warn_fails_when_the_hook_stays_silent_above_the_step(tmp_path: Path) -> None:
    silent = tmp_path / "plugin"
    (silent / "hooks").mkdir(parents=True)
    (silent / "hooks" / "context-warn.mjs").write_text("process.exit(0)\n")
    check = check_context_warn(silent, tmp_path / "state", run_input)
    assert not check.passed and "did not warn" in check.detail


def copy_plugin(tmp_path: Path) -> Path:
    copy = tmp_path / "plugin"
    shutil.copytree(PLUGIN, copy)
    return copy


def test_agents_pass_on_the_real_plugin() -> None:
    assert check_agents(PLUGIN).passed


def test_agents_fail_naming_the_file_without_tools(tmp_path: Path) -> None:
    copy = copy_plugin(tmp_path)
    agent = copy / "agents" / "reviewer-sonnet.md"
    agent.write_text("".join(line for line in agent.read_text().splitlines(True) if not line.startswith("tools:")))
    check = check_agents(copy)
    assert not check.passed and "reviewer-sonnet.md" in check.detail and "tools" in check.detail


def test_agents_fail_without_frontmatter(tmp_path: Path) -> None:
    copy = copy_plugin(tmp_path)
    (copy / "agents" / "implementer-haiku.md").write_text("no frontmatter")
    check = check_agents(copy)
    assert not check.passed and "implementer-haiku.md" in check.detail


def test_tests_pass_when_the_command_exits_zero(tmp_path: Path) -> None:
    assert check_tests(tmp_path, "true", run_input).passed


def test_tests_fail_says_the_failure_may_predate_the_kit(tmp_path: Path) -> None:
    check = check_tests(tmp_path, "false", run_input)
    assert not check.passed
    assert check.detail == "false failed; this may predate the kit: run it on the default branch to compare"


def test_tests_run_in_the_repo(tmp_path: Path) -> None:
    (tmp_path / "marker").write_text("")
    assert check_tests(tmp_path, "test -f marker", run_input).passed


@needs_node
def test_run_checks_returns_the_five_checks_in_order(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, LAYERS)
    checks = run_checks(PLUGIN, repo, LAYERS, "true", tmp_path / "state", run_input)
    assert [c.name for c in checks] == ["settings", "guard", "context-warn", "agents", "tests"]
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


@needs_node
def test_run_checks_runs_every_check_even_after_a_failure(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, LAYERS)
    (repo / ".claude" / "settings.json").write_text("{nope")
    checks = run_checks(PLUGIN, repo, LAYERS, "false", tmp_path / "state", run_input)
    assert [c.passed for c in checks] == [False, True, True, True, False]


def missing_program(cmd: list[str], cwd: Path, stdin: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: not found (boom)")


def test_guard_fails_naming_a_missing_node(tmp_path: Path) -> None:
    check = check_guard(PLUGIN, repo_with(tmp_path, LAYERS), LAYERS, missing_program)
    assert not check.passed and "node: not found" in check.detail


def test_context_warn_fails_naming_a_missing_node(tmp_path: Path) -> None:
    check = check_context_warn(PLUGIN, tmp_path, missing_program)
    assert not check.passed and "node: not found" in check.detail


def test_tests_fail_naming_a_missing_shell(tmp_path: Path) -> None:
    check = check_tests(tmp_path, "true", missing_program)
    assert not check.passed and "sh: not found" in check.detail and "may predate the kit" in check.detail


def test_run_checks_reports_every_check_when_programs_are_missing(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, LAYERS)
    checks = run_checks(PLUGIN, repo, LAYERS, "true", tmp_path / "state", missing_program)
    assert [c.passed for c in checks] == [True, False, False, True, False]


@needs_node
def test_verify_uses_a_scratch_dir_inside_kit_home_and_removes_it(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, LAYERS)
    home = tmp_path / "kit-home"
    home.mkdir()
    checks = verify(PLUGIN, repo, LAYERS, "true", home, run_input)
    assert all(c.passed for c in checks)
    assert list(home.iterdir()) == []


def test_verify_removes_the_scratch_dir_when_every_program_is_missing(tmp_path: Path) -> None:
    home = tmp_path / "kit-home"
    home.mkdir()
    verify(PLUGIN, repo_with(tmp_path, LAYERS), LAYERS, "true", home, missing_program)
    assert list(home.iterdir()) == []


def test_require_passing_is_silent_when_every_check_passed() -> None:
    require_passing([Check("a", True, "ok")], "chore/claude-kit-v0.1.0")


def test_require_passing_lists_failures_and_names_the_branch() -> None:
    checks = [Check("a", True, "ok"), Check("tests", False, "boom"), Check("guard", False, "bad")]
    with pytest.raises(KitError) as raised:
        require_passing(checks, "chore/claude-kit-v0.1.0")
    message = str(raised.value)
    assert "tests: boom" in message and "guard: bad" in message and "a: ok" not in message
    assert "branch chore/claude-kit-v0.1.0 left for inspection; no PR" in message


def test_check_line_marks_pass_and_fail() -> None:
    assert check_line(Check("a", True, "ok")) == "PASS a: ok"
    assert check_line(Check("a", False, "no")) == "FAIL a: no"
