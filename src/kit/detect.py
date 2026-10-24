"""Deterministic detection of a python-uv repo's test layout; no LLM."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from kit.errors import KitError

UNSUPPORTED = "unsupported stack: no language pack for this repo (supported: python-uv)"
LAYERS_PATH = ".claude/test-layers.json"
GUARD_PATH = ".claude/hooks/test-layer-guard.mjs"
PIPELINE_TEST = "tests/test_cli_pipeline.py"
TEST_COMMAND = "uv run pytest -q"
CONVENTIONS_DOC = "docs/code-conventions.md"
WIRING_MODULES = ("cli", "pipeline")
CALL_IN_REGEX_SOURCE = re.compile(r"\\b(\w+)\\s\*\\\(")
PYTEST_DEPENDENCY = re.compile(r"\s*pytest(?![\w.-])")
FLAGS = {
    "test_command": "--test-command",
    "pipeline_test": "--pipeline-test",
    "wiring_functions": "--wiring-functions",
}


REQUIRED = ("test_command", "pipeline_test")
Ask = Callable[[str, str], str]


@dataclass(frozen=True)
class Detected:
    """What detect found. An unresolved key holds its proposal (empty if none)."""

    package: str
    test_command: str
    pipeline_test: str
    wiring_modules: tuple[str, ...]
    wiring_functions: tuple[str, ...]
    unresolved: tuple[str, ...]


def wiring_functions_from_guard(text: str) -> tuple[str, ...]:
    """Names called as `\\bname\\s*\\(` in the guard's WIRING regex source."""
    return tuple(dict.fromkeys(CALL_IN_REGEX_SOURCE.findall(text)))


def _load_pyproject(repo: Path) -> dict:
    try:
        return tomllib.loads((repo / "pyproject.toml").read_text())
    except tomllib.TOMLDecodeError as error:
        raise KitError(f"pyproject.toml is not valid TOML: {error}") from error


def _package(project: dict) -> str:
    scripts = project.get("scripts") or {}
    if scripts:
        return str(next(iter(scripts.values()))).split(":")[0].split(".")[0]
    name = project.get("name")
    if not name:
        raise KitError("pyproject.toml has no [project] name to derive the package from")
    return str(name).replace("-", "_")


def _has_pytest(pyproject: dict) -> bool:
    groups = list((pyproject.get("dependency-groups") or {}).values())
    groups += list((pyproject.get("project", {}).get("optional-dependencies") or {}).values())
    return any(isinstance(dep, str) and PYTEST_DEPENDENCY.match(dep) for group in groups for dep in group)


def _module_path(repo: Path, package: str, module: str) -> Path | None:
    for candidate in (repo / "src" / package / f"{module}.py", repo / package / f"{module}.py"):
        if candidate.is_file():
            return candidate
    return None


def _run_functions(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return ()
    return tuple(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("run_")
    )


def detect(repo: Path) -> Detected:
    if not (repo / "pyproject.toml").is_file() or not (repo / "uv.lock").is_file():
        raise KitError(UNSUPPORTED)
    pyproject = _load_pyproject(repo)
    package = _package(pyproject.get("project", {}))
    unresolved: list[str] = []

    test_command = TEST_COMMAND if _has_pytest(pyproject) else ""
    if not test_command:
        unresolved.append("test_command")

    pipeline_test = PIPELINE_TEST if (repo / PIPELINE_TEST).is_file() else ""
    if not pipeline_test:
        unresolved.append("pipeline_test")

    modules = tuple(m for m in WIRING_MODULES if _module_path(repo, package, m))

    guard = repo / GUARD_PATH
    if guard.is_file():
        functions = wiring_functions_from_guard(guard.read_text())
    else:
        functions = _run_functions(_module_path(repo, package, "pipeline"))
        unresolved.append("wiring_functions")

    return Detected(package, test_command, pipeline_test, modules, functions, tuple(unresolved))


def _split(answer: str) -> tuple[str, ...]:
    return tuple(name.strip() for name in answer.split(",") if name.strip())


def _proposal(d: Detected, key: str) -> str:
    return ",".join(d.wiring_functions) if key == "wiring_functions" else getattr(d, key)


def _apply(d: Detected, key: str, answer: str) -> Detected:
    value = _split(answer) if key == "wiring_functions" else answer.strip()
    return replace(d, **{key: value})


def previous_answers(repo: Path, d: Detected) -> dict[str, str]:
    """On an upgrade the local guard is gone; the wiring functions then come from the last apply's test-layers.json."""
    if "wiring_functions" not in d.unresolved:
        return {}
    try:
        recorded = json.loads((repo / LAYERS_PATH).read_text())["wiring_functions"]
        if not isinstance(recorded, list) or not all(isinstance(name, str) for name in recorded):
            return {}
        return {"wiring_functions": ",".join(recorded)}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def checked_answer(key: str, value: str) -> str:
    """An empty test_command or pipeline_test would silently disable the guard or the checks."""
    if key in REQUIRED and not value.strip():
        raise KitError(f"{FLAGS[key]} needs a non-empty value")
    return value


def checked_answers(answers: dict[str, str]) -> dict[str, str]:
    return {key: checked_answer(key, value) for key, value in answers.items()}


def checked_ask(ask: Ask | None) -> Ask | None:
    return None if ask is None else lambda key, proposal: checked_answer(key, ask(key, proposal))


def ask_with_default(read: Callable[[str], str]) -> Ask:
    return lambda key, proposal: read(f"{key} [{proposal}]: ") or proposal


def resolve(d: Detected, answers: dict[str, str], ask: Ask | None) -> Detected:
    """Apply flag answers over detection, then ask for what is still unresolved."""
    for key in FLAGS:
        if key in answers:
            d = _apply(d, key, answers[key])
    pending = tuple(key for key in d.unresolved if key not in answers)
    if pending and ask is None:
        flags = ", ".join(FLAGS[key] for key in pending)
        raise KitError(f"cannot detect {', '.join(pending)}; pass {flags}")
    for key in pending:
        d = _apply(d, key, ask(key, _proposal(d, key)))  # type: ignore[misc]
    return replace(d, unresolved=())


def test_layers_json(d: Detected) -> dict:
    """The config plugin/hooks/test-layer-guard.mjs reads."""
    return {
        "pipeline_test": d.pipeline_test,
        "package": d.package,
        "wiring_modules": list(d.wiring_modules),
        "wiring_functions": list(d.wiring_functions),
        "conventions_doc": CONVENTIONS_DOC,
    }
