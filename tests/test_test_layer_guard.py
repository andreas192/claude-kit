"""UNIT: plugin/hooks/test-layer-guard.mjs, run under node with a config built in code."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parents[1] / "plugin" / "hooks" / "test-layer-guard.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

DGI = {
    "pipeline_test": "tests/test_cli_pipeline.py",
    "package": "dgi",
    "wiring_modules": ["cli", "pipeline"],
    "wiring_functions": ["run_refresh"],
    "conventions_doc": "docs/code-conventions.md",
}
INVEST = {**DGI, "package": "invest", "wiring_functions": ["run_all"]}


def run(tmp_path: Path, config: dict | str | None, file: str, text: str) -> dict:
    if config is not None:
        (tmp_path / ".claude").mkdir(exist_ok=True)
        body = config if isinstance(config, str) else json.dumps(config)
        (tmp_path / ".claude" / "test-layers.json").write_text(body)
    payload = {"tool_name": "Write", "tool_input": {"file_path": file, "content": text}}
    done = subprocess.run(
        ["node", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": shutil.which("node").rsplit("/", 1)[0], "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    return json.loads(done.stdout) if done.stdout else {}


@pytest.mark.parametrize(
    "config,text",
    [
        (DGI, "from dgi.pipeline import run_refresh"),
        (DGI, "result = CliRunner().invoke(app)"),
        (DGI, "run_refresh (settings)"),
        (DGI, "import dgi.cli"),
        (DGI, "from dgi import pipeline"),
        (INVEST, "run_all(settings)"),
        (INVEST, "from invest.cli import app"),
        (INVEST, "import invest.pipeline"),
    ],
)
def test_wiring_in_a_unit_test_is_denied(tmp_path: Path, config: dict, text: str) -> None:
    out = run(tmp_path, config, "/r/tests/test_x.py", text)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "docs/code-conventions.md" in out["permissionDecisionReason"]


def test_pipeline_test_file_gets_the_layer_contract(tmp_path: Path) -> None:
    out = run(tmp_path, DGI, "/r/tests/test_cli_pipeline.py", "from dgi.cli import app")["hookSpecificOutput"]
    assert "PIPELINE layer" in out["additionalContext"] and "permissionDecision" not in out


@pytest.mark.parametrize(
    "file,text",
    [
        ("/r/tests/test_x.py", "from dgi.metrics import x"),
        ("/r/src/dgi/x.py", "from dgi.cli import app"),
        ("/r/tests/test_x.py", "import dgi.cli_helpers"),
        ("/r/tests/test_x.py", "run_refresher(x)"),
    ],
)
def test_other_writes_pass_silently(tmp_path: Path, file: str, text: str) -> None:
    assert run(tmp_path, DGI, file, text) == {}


@pytest.mark.parametrize("config", [None, "{not json", {"package": "dgi"}])
def test_missing_or_bad_config_never_blocks(tmp_path: Path, config: dict | str | None) -> None:
    assert run(tmp_path, config, "/r/tests/test_x.py", "CliRunner()") == {}
