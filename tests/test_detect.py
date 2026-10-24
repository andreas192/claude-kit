import json
from pathlib import Path

import pytest

from kit import detect as detection
from kit.detect import ask_with_default, checked_answers, checked_ask, detect, previous_answers, resolve, wiring_functions_from_guard
from kit.errors import KitError

# Real WIRING lines, verbatim from dividend-growth and investment.
DGI_WIRING = r"const WIRING = /\bCliRunner\b|\brun_refresh\s*\(|from dgi\.(cli|pipeline) import|import dgi\.(cli|pipeline)\b|from dgi import (cli|pipeline)\b/;"
INVEST_WIRING = r"const WIRING = /\bCliRunner\b|\brun_all\s*\(|from invest\.(cli|pipeline) import|import invest\.(cli|pipeline)|from invest import (cli|pipeline)\b/;"

PYPROJECT = """[project]
name = "{name}"
version = "0.1.0"
dependencies = ["typer>=0.12"]

[dependency-groups]
dev = [{dev}]

[project.scripts]
{script} = "{script}.cli:app"
"""


def build_repo(root: Path, package: str, wiring: str, entry: str, dev: str = '"pytest>=8"') -> Path:
    (root / "pyproject.toml").write_text(PYPROJECT.format(name=package, script=package, dev=dev))
    (root / "uv.lock").write_text("")
    src = root / "src" / package
    src.mkdir(parents=True)
    (src / "cli.py").write_text("app = None\n")
    (src / "pipeline.py").write_text(f"def helper(): ...\n\ndef {entry}(): ...\n\ndef run_rescore(): ...\n")
    (root / "tests").mkdir()
    (root / "tests/test_cli_pipeline.py").write_text("")
    hooks = root / ".claude/hooks"
    hooks.mkdir(parents=True)
    (hooks / "test-layer-guard.mjs").write_text(f"// guard\n{wiring}\n")
    return root


@pytest.fixture
def dgi_repo(tmp_path):
    return build_repo(tmp_path, "dgi", DGI_WIRING, "run_refresh")


@pytest.fixture
def invest_repo(tmp_path):
    return build_repo(tmp_path, "invest", INVEST_WIRING, "run_all")


def test_dgi_shape(dgi_repo):
    d = detect(dgi_repo)
    assert (d.package, d.test_command, d.pipeline_test, d.wiring_modules, d.wiring_functions, d.unresolved) == (
        "dgi", "uv run pytest -q", "tests/test_cli_pipeline.py", ("cli", "pipeline"), ("run_refresh",), ())


def test_invest_shape(invest_repo):
    assert detect(invest_repo).wiring_functions == ("run_all",)


def test_guard_extraction_skips_cli_runner():
    assert wiring_functions_from_guard(DGI_WIRING) == ("run_refresh",)
    assert wiring_functions_from_guard(INVEST_WIRING) == ("run_all",)


def test_without_a_guard_the_wiring_functions_are_asked(dgi_repo):
    (dgi_repo / ".claude/hooks/test-layer-guard.mjs").unlink()
    d = detect(dgi_repo)
    assert d.unresolved == ("wiring_functions",)
    asked = {}
    r = resolve(d, {}, lambda key, proposal: asked.setdefault(key, proposal) and "run_refresh")
    assert asked["wiring_functions"] == "run_refresh,run_rescore" and r.wiring_functions == ("run_refresh",)
    assert r.unresolved == ()
    with pytest.raises(KitError, match="--wiring-functions"):
        resolve(d, {}, None)


def test_no_guard_and_no_pipeline_module_proposes_nothing(dgi_repo):
    (dgi_repo / ".claude/hooks/test-layer-guard.mjs").unlink()
    (dgi_repo / "src/dgi/pipeline.py").unlink()
    d = detect(dgi_repo)
    assert d.wiring_modules == ("cli",)
    asked = {}
    resolve(d, {}, lambda key, proposal: asked.setdefault(key, proposal) or "run_x")
    assert asked == {"wiring_functions": ""}


def test_answers_override_detection(dgi_repo):
    assert resolve(detect(dgi_repo), {"test_command": "true"}, None).test_command == "true"


def test_answer_for_wiring_functions_is_split_and_stripped(dgi_repo):
    (dgi_repo / ".claude/hooks/test-layer-guard.mjs").unlink()
    r = resolve(detect(dgi_repo), {"wiring_functions": " run_a , run_b "}, None)
    assert r.wiring_functions == ("run_a", "run_b") and r.unresolved == ()


def test_missing_pytest_and_pipeline_test_are_unresolved_and_named_by_flags(dgi_repo):
    (dgi_repo / "pyproject.toml").write_text(PYPROJECT.format(name="dgi", script="dgi", dev='"ruff"'))
    (dgi_repo / "tests/test_cli_pipeline.py").unlink()
    d = detect(dgi_repo)
    assert d.unresolved == ("test_command", "pipeline_test")
    with pytest.raises(KitError, match="--test-command, --pipeline-test"):
        resolve(d, {}, None)
    r = resolve(d, {"test_command": "make test"}, lambda key, proposal: "tests/test_cli_pipeline.py")
    assert (r.test_command, r.pipeline_test, r.unresolved) == ("make test", "tests/test_cli_pipeline.py", ())


def test_package_falls_back_to_project_name(dgi_repo):
    (dgi_repo / "pyproject.toml").write_text('[project]\nname = "my-app"\n[dependency-groups]\ndev = ["pytest"]\n')
    (dgi_repo / "src" / "dgi").rename(dgi_repo / "src" / "my_app")
    assert detect(dgi_repo).package == "my_app"


def test_a_repo_without_cli_or_pipeline_modules_is_refused(dgi_repo):
    (dgi_repo / "src" / "dgi" / "cli.py").unlink()
    (dgi_repo / "src" / "dgi" / "pipeline.py").unlink()
    with pytest.raises(KitError, match=r"no wiring modules \(cli.py/pipeline.py\) under"):
        detect(dgi_repo)


def test_test_layers_json_is_the_hook_config(dgi_repo):
    assert detection.test_layers_json(detect(dgi_repo)) == {
        "pipeline_test": "tests/test_cli_pipeline.py",
        "package": "dgi",
        "wiring_modules": ["cli", "pipeline"],
        "wiring_functions": ["run_refresh"],
        "conventions_doc": "docs/code-conventions.md",
    }


def test_unsupported_stack(tmp_path):
    with pytest.raises(KitError, match="python-uv"):
        detect(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    with pytest.raises(KitError, match="python-uv"):
        detect(tmp_path)


def test_empty_flag_answers_for_test_command_and_pipeline_test_are_refused():
    for key, flag in (("test_command", "--test-command"), ("pipeline_test", "--pipeline-test")):
        with pytest.raises(KitError, match=flag):
            checked_answers({key: "  "})


def test_empty_wiring_functions_answer_is_allowed():
    assert checked_answers({"wiring_functions": ""}) == {"wiring_functions": ""}


def test_checked_ask_refuses_an_empty_answer_naming_the_flag():
    ask = checked_ask(lambda key, proposal: "")
    with pytest.raises(KitError, match="--pipeline-test"):
        ask("pipeline_test", "tests/test_cli_pipeline.py")
    assert ask("wiring_functions", "") == ""


def test_checked_ask_passes_a_real_answer_through_and_none_stays_none():
    assert checked_ask(lambda key, proposal: "uv run pytest")("test_command", "") == "uv run pytest"
    assert checked_ask(None) is None


def test_ask_with_default_returns_the_proposal_on_an_empty_line():
    prompts = []
    ask = ask_with_default(lambda prompt: prompts.append(prompt) or "")
    assert ask("test_command", "uv run pytest -q") == "uv run pytest -q"
    assert "test_command" in prompts[0] and "uv run pytest -q" in prompts[0]
    assert ask_with_default(lambda prompt: "other")("test_command", "x") == "other"


def write_layers(repo, functions):
    (repo / ".claude/test-layers.json").write_text(json.dumps({"wiring_functions": functions}))


def test_previous_answers_take_the_wiring_functions_from_the_last_apply(dgi_repo):
    (dgi_repo / ".claude/hooks/test-layer-guard.mjs").unlink()
    write_layers(dgi_repo, ["run_a", "run_b"])
    d = detect(dgi_repo)
    assert previous_answers(dgi_repo, d) == {"wiring_functions": "run_a,run_b"}
    assert resolve(d, previous_answers(dgi_repo, d), None).wiring_functions == ("run_a", "run_b")


def test_previous_answers_are_ignored_while_the_guard_still_says_it(dgi_repo):
    write_layers(dgi_repo, ["stale"])
    assert previous_answers(dgi_repo, detect(dgi_repo)) == {}


@pytest.mark.parametrize("text", [None, "{oops", "[]", "{}", '{"wiring_functions": 3}', '{"wiring_functions": "run"}', '{"wiring_functions": [1]}'])
def test_previous_answers_fall_back_to_asking_when_the_file_is_unusable(dgi_repo, text):
    (dgi_repo / ".claude/hooks/test-layer-guard.mjs").unlink()
    if text is not None:
        (dgi_repo / ".claude/test-layers.json").write_text(text)
    assert previous_answers(dgi_repo, detect(dgi_repo)) == {}
