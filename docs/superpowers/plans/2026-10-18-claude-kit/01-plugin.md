# Phase 1: repo and plugin (tasks 1–3)

Index and global constraints: `../2026-10-18-claude-kit.md`. Sources copied from dividend-growth are read, never edited, in `../dividend-growth`.

### Task 1: Repo scaffold and starter files

Model: haiku

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `CLAUDE.md`, `docs/command.md`, `docs/code-conventions.md`
- Create: `src/kit/__init__.py`, `src/kit/errors.py`, `src/kit/cli.py`
- Create: `starter/CLAUDE.md`, `starter/docs/code-conventions.md`, `starter/docs/token-strategy.md`, `starter/permissions.json`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `kit.errors.KitError(Exception)`; `kit.cli.main(argv: list[str] | None = None) -> int` (argparse, subcommands added by later tasks; `KitError` caught in `main`, printed as `error: <message>` on stderr, returns 1).

- [ ] **Step 1: Write the failing test** (UNIT, proves `main`)

```python
def test_version_prints_package_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "kit 0.1.0"

def test_kit_error_becomes_exit_1(capsys, monkeypatch):
    monkeypatch.setattr(cli, "dispatch", lambda args: (_ for _ in ()).throw(KitError("boom")))
    assert main(["status"]) == 1
    assert capsys.readouterr().err.strip() == "error: boom"
```

- [ ] **Step 2: Run** `uv sync && uv run pytest tests/test_cli.py` — expect FAIL (no module `kit`).
- [ ] **Step 3: Create the files.**
  - `pyproject.toml`: project `claude-kit`, version `0.1.0`, `requires-python = ">=3.12"`, `dependencies = []`, `[project.scripts] kit = "kit.cli:main"`, `[dependency-groups] dev = ["pytest"]`, hatchling build with `packages = ["src/kit"]`, `[tool.pytest.ini_options] addopts = "-q"`, `testpaths = ["tests"]`. Package data: include `src/kit/known_hashes.json` (created in task 12).
  - `.python-version`: `3.12`. `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`.
  - `cli.py`: `main` parses `--version` and a `status` subcommand placeholder, calls `dispatch(args) -> int`; `dispatch` returns 0 for now.
  - `docs/code-conventions.md`: copy `../dividend-growth/docs/code-conventions.md`, then: replace `DgiError` with `KitError` and `dgi/errors.py` with `kit/errors.py`; delete the bullet starting "Transforms are SQL (DuckDB)"; replace "`cli.py` commands and `pipeline.py` are wiring" with "`cli.py`, `apply.py` and `bench/run.py` are wiring"; leave the rest.
  - `CLAUDE.md` (under 40 lines): what the kit is (one paragraph from the spec "Why"), the spec and plan paths, the Global Constraints of the plan index as bullets, "Test command: `uv run pytest -q`", and "Commands live in `docs/command.md`".
  - `docs/command.md`: `uv sync`; `uv run pytest -q`; `uv run --project ~/Projects/Personal/claude-kit kit apply <repo> [--version vX.Y.Z]`; `... kit bench <repo> --control <repo>`; `... kit status`; release: `git tag vX.Y.Z` after bumping `plugin/.claude-plugin/plugin.json` and `pyproject.toml`.
  - `starter/`: `CLAUDE.md` is a skeleton with headings only (`# <Project>`, `## Stack`, `## Rules to follow`, `## Testing` with the line "Test command: see `.claude/kit.json` `test_command`.", `## Working conventions`); `docs/code-conventions.md` is the copy made above; `docs/token-strategy.md` is `../dividend-growth/docs/token-strategy.md` with agent names changed to `kit:implementer-sonnet`, `kit:implementer-haiku`, `kit:reviewer-sonnet`, `.claude/hooks/context-warn.mjs` changed to "the kit's `context-warn` hook", `scripts/token_report.py` changed to `kit bench`, `--project ../investment` changed to `--control <repo>`, and the Brainstorm row's "Reference only the spec and `../investment/GOLD_SCHEMA.md`" changed to "Reference only the spec"; `permissions.json` is `{"allow": ["Bash(git status *)", "Bash(git show *)", "Bash(grep *)"]}`.
- [ ] **Step 4: Run** `uv run pytest tests/test_cli.py` — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "chore: scaffold claude-kit"`

### Task 2: Plugin manifest, agents and `context-warn`

Model: sonnet

**Files:**
- Create: `plugin/.claude-plugin/plugin.json`, `plugin/agents/implementer-haiku.md`, `plugin/agents/implementer-sonnet.md`, `plugin/agents/reviewer-sonnet.md`, `plugin/hooks/hooks.json`, `plugin/hooks/context-warn.mjs`
- Create: `src/kit/frontmatter.py`
- Test: `tests/test_context_warn_hook.py`, `tests/test_plugin_files.py`

**Interfaces:**
- Produces: `kit.frontmatter.parse_frontmatter(text: str) -> dict[str, str]` (keys and raw string values between the leading `---` lines; `KitError` if there is no frontmatter). `plugin/hooks/context-warn.mjs` exports `lastContext(lines)`, `warnLevel(context, warned)`, `messages(context, strategyDoc: boolean)`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_context_warn_hook.py`: copy `../dividend-growth/tests/test_context_warn_hook.py`; point `HOOK` at `plugin/hooks/context-warn.mjs`; rename env `DGI_CONTEXT_WARN_STEP` to `KIT_CONTEXT_WARN_STEP`; add `CLAUDE_PROJECT_DIR` to the env (a `tmp_path / "repo"` dir). Add:

```python
def test_names_the_strategy_doc_only_if_the_repo_has_it(tmp_path):
    text = lambda: run(tmp_path, [assistant(100_000)], event="UserPromptSubmit", session=str(len(list(tmp_path.iterdir()))))["hookSpecificOutput"]["additionalContext"]
    assert "docs/token-strategy.md" not in text()
    (tmp_path / "repo" / "docs").mkdir(parents=True); (tmp_path / "repo" / "docs" / "token-strategy.md").write_text("x")
    assert "docs/token-strategy.md" in text()

def test_state_file_has_no_dgi_prefix(tmp_path):
    run(tmp_path, [assistant(100_000)])
    assert [p.name for p in tmp_path.glob("kit-context-warn-*")] and not list(tmp_path.glob("dgi-*"))
```

  - `tests/test_plugin_files.py` (UNIT, proves the plugin files and `parse_frontmatter`):

```python
def test_plugin_manifest_name_and_version():
    m = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert (m["name"], m["version"]) == ("kit", tomllib.loads(PYPROJECT.read_text())["project"]["version"])

def test_every_agent_has_routing_frontmatter():
    for path in (PLUGIN / "agents").glob("*.md"):
        fm = parse_frontmatter(path.read_text())
        assert {"name", "description", "model", "effort", "tools"} <= fm.keys()
        assert "uv run pytest" not in path.read_text()
        assert "test_command" in path.read_text()

def test_hooks_json_points_at_existing_scripts():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    assert set(hooks) == {"PreToolUse", "Stop", "UserPromptSubmit"}
    for group in [g for groups in hooks.values() for g in groups]:
        for h in group["hooks"]:
            script = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(hooks/[\w-]+\.mjs)", h["command"]).group(1)
            assert (PLUGIN / script).exists()

def test_parse_frontmatter_without_header_raises():
    with pytest.raises(KitError):
        parse_frontmatter("no header")
```

- [ ] **Step 2: Run** `uv run pytest tests/test_context_warn_hook.py tests/test_plugin_files.py` — expect FAIL.
- [ ] **Step 3: Create the plugin.**
  - `plugin.json`: `{"name": "kit", "version": "0.1.0", "description": "Shared Claude Code agents and hooks (claude-kit)", "author": {"name": "Andrei Luculescu"}}`.
  - Agents: copy the three files from `../dividend-growth/.claude/agents/` unchanged except the test line, which becomes "Run the test command from `.claude/kit.json` (`test_command`) on the tasks' test files only while iterating." in the implementers and "Run the test command from `.claude/kit.json` (`test_command`) on the changed test files only." in the reviewer; and "Follow `docs/code-conventions.md`" becomes "Follow `docs/code-conventions.md` if the repo has one".
  - `hooks.json`: `PreToolUse` matcher `Write|Edit` → `node "${CLAUDE_PLUGIN_ROOT}/hooks/test-layer-guard.mjs"` (file created in task 3); `Stop` and `UserPromptSubmit` → `node "${CLAUDE_PLUGIN_ROOT}/hooks/context-warn.mjs"`, wrapped in a top-level `"hooks"` key.
  - `context-warn.mjs`: copy dividend-growth's; env `KIT_CONTEXT_WARN_STEP` (default 80000); state file `kit-context-warn-<session>-<event>`; `messages(context, strategyDoc)` names `docs/token-strategy.md` only when `strategyDoc` is true (otherwise "the checkpoint" with no file); `main` sets `strategyDoc` from `existsSync(join(process.env.CLAUDE_PROJECT_DIR ?? "", "docs/token-strategy.md"))`.
  - `frontmatter.py`: `parse_frontmatter` as above, `key: value` lines only.
- [ ] **Step 4: Run** the two test files — expect PASS (hook test also needs task 3's file only for `test_hooks_json_points_at_existing_scripts`; create an empty `plugin/hooks/test-layer-guard.mjs` placeholder now, task 3 fills it).
- [ ] **Step 5: Commit** `git commit -am "feat(plugin): kit agents and context-warn hook"` (add new files first).

### Task 3: Config-driven test-layer guard

Model: sonnet

**Files:**
- Modify: `plugin/hooks/test-layer-guard.mjs`
- Test: `tests/test_test_layer_guard.py`

**Interfaces:**
- Consumes: `<CLAUDE_PROJECT_DIR>/.claude/test-layers.json`: `{"pipeline_test": "tests/test_cli_pipeline.py", "package": "dgi", "wiring_modules": ["cli", "pipeline"], "wiring_functions": ["run_refresh"], "conventions_doc": "docs/code-conventions.md"}`.
- Produces: the hook exports `buildRules(config) -> {pipelineTest, anyTest, wiring}` (RegExps) and `decide(rules, file, text, doc) -> object | null` (the `hookSpecificOutput` body, or null). Tasks 11 and 13 write and probe this file.

Rules built from the config (same effect as both current hooks):
- `pipelineTest`: `(^|/)` + escaped `pipeline_test` + `$`.
- `anyTest`: `(^|/)` + escaped dirname of `pipeline_test` + `/[^/]+\.py$`.
- `wiring`: `\bCliRunner\b`, then `\b<fn>\s*\(` per function, then `from <pkg>\.(<mods>) import`, `import <pkg>\.(<mods>)\b`, `from <pkg> import (<mods>)\b`, joined with `|`.

- [ ] **Step 1: Write the failing tests** (UNIT, runs the hook under `node` like task 2; `pytestmark` skips without node). Helper `run(tmp_path, config: dict | str | None, file: str, text: str) -> dict` writes the config (a dict as JSON, a str verbatim, None for no file) into `tmp_path/.claude/test-layers.json` and runs the hook with `CLAUDE_PROJECT_DIR=tmp_path`.

```python
DGI = {"pipeline_test": "tests/test_cli_pipeline.py", "package": "dgi", "wiring_modules": ["cli", "pipeline"], "wiring_functions": ["run_refresh"], "conventions_doc": "docs/code-conventions.md"}
INVEST = {**DGI, "package": "invest", "wiring_functions": ["run_all"]}

@pytest.mark.parametrize("config,text", [
    (DGI, "from dgi.pipeline import run_refresh"), (DGI, "result = CliRunner().invoke(app)"),
    (DGI, "run_refresh (settings)"), (DGI, "import dgi.cli"), (DGI, "from dgi import pipeline"),
    (INVEST, "run_all(settings)"), (INVEST, "from invest.cli import app"), (INVEST, "import invest.pipeline"),
])
def test_wiring_in_a_unit_test_is_denied(tmp_path, config, text):
    out = run(tmp_path, config, "/r/tests/test_x.py", text)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "docs/code-conventions.md" in out["permissionDecisionReason"]

def test_pipeline_test_file_gets_the_layer_contract(tmp_path):
    out = run(tmp_path, DGI, "/r/tests/test_cli_pipeline.py", "from dgi.cli import app")["hookSpecificOutput"]
    assert "PIPELINE layer" in out["additionalContext"] and "permissionDecision" not in out

@pytest.mark.parametrize("file,text", [
    ("/r/tests/test_x.py", "from dgi.metrics import x"), ("/r/src/dgi/x.py", "from dgi.cli import app"),
    ("/r/tests/test_x.py", "import dgi.cli_helpers"), ("/r/tests/test_x.py", "run_refresher(x)"),
])
def test_other_writes_pass_silently(tmp_path, file, text):
    assert run(tmp_path, DGI, file, text) == {}

@pytest.mark.parametrize("config", [None, "{not json", {"package": "dgi"}])
def test_missing_or_bad_config_never_blocks(tmp_path, config):
    assert run(tmp_path, config, "/r/tests/test_x.py", "CliRunner()") == {}
```

- [ ] **Step 2: Run** `uv run pytest tests/test_test_layer_guard.py` — expect FAIL.
- [ ] **Step 3: Implement** the hook: read stdin as today; read the config with try/catch (missing file, bad JSON or a missing key → exit 0 with no output); `buildRules`, `decide`; message texts as in `../dividend-growth/.claude/hooks/test-layer-guard.mjs` with `docs/code-conventions.md` replaced by `conventions_doc`.
- [ ] **Step 4: Run** the test file — expect PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(plugin): config-driven test-layer guard"`.

Known difference, to list in the release notes: investment's current regex has no `\b` after `import invest\.(cli|pipeline)`, so it also denied `import invest.cli_helpers`; the kit allows that line. Nothing in investment imports such a module today.
