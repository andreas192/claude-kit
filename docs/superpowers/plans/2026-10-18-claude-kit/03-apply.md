# Phase 3: `kit apply` (tasks 9–14)

Index and global constraints: `../2026-10-18-claude-kit.md`. Steps: spec, "`kit apply <repo> [--version vX.Y.Z]`"; names and snapshot layout: spec, "Builder decisions".

### Task 9: Version snapshot

Model: sonnet

**Files:**
- Create: `src/kit/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `kit.gitrun.Runner`, `run` (task 6).
- Produces: `marketplace_name(version: str) -> str` (`"v0.1.0"` → `"kit-v0-1-0"`; `KitError` unless `^v\d+\.\d+\.\d+$`); `latest_tag(kit_repo: Path, run: Runner) -> str` (highest semver `v*` tag; `KitError("no release tag")` if none); `tree_digest(path: Path) -> str` (SHA-256 over sorted relative paths and file bytes); `snapshot(kit_repo: Path, version: str, kit_home: Path, run: Runner) -> Path` (returns `kit_home/<version>`).

`snapshot` exports `git archive --format=tar <version>:plugin` into a temp dir beside the target as `plugins/kit/`, writes `.claude-plugin/marketplace.json` = `{"name": marketplace_name(version), "owner": {"name": "claude-kit"}, "plugins": [{"name": "kit", "source": "./plugins/kit", "description": "claude-kit <version>"}]}`, checks `plugins/kit/.claude-plugin/plugin.json` `version` equals the version without `v` (else `KitError`), then: target missing → `os.replace(temp, target)`; target present with the same `tree_digest` → remove temp, return target; different → remove temp, `KitError("snapshot <path> differs from tag <version>; it must never change. Move it aside and re-run.")`.

- [ ] **Step 1: Write the failing tests** (temp kit repo built in code: `plugin/.claude-plugin/plugin.json` with version `0.1.0`, one agent file, tagged `v0.1.0`):

```python
def test_marketplace_name():
    assert marketplace_name("v1.12.3") == "kit-v1-12-3"
    with pytest.raises(KitError): marketplace_name("1.2")

def test_snapshot_writes_marketplace_and_plugin(kit_repo, tmp_path):
    path = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    m = json.loads((path / ".claude-plugin/marketplace.json").read_text())
    assert m["name"] == "kit-v0-1-0" and (path / "plugins/kit/agents/a.md").exists()

def test_second_snapshot_is_a_no_op_and_ignores_the_working_tree(kit_repo, tmp_path):
    first = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    (kit_repo / "plugin/agents/a.md").write_text("edited, not tagged")
    assert snapshot(kit_repo, "v0.1.0", tmp_path / "home", run) == first
    assert "edited" not in (first / "plugins/kit/agents/a.md").read_text()

def test_changed_snapshot_is_refused(kit_repo, tmp_path):
    path = snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)
    (path / "plugins/kit/agents/a.md").write_text("tampered")
    with pytest.raises(KitError, match="must never change"):
        snapshot(kit_repo, "v0.1.0", tmp_path / "home", run)

def test_plugin_version_must_match_the_tag(kit_repo, tmp_path):
    tag(kit_repo, "v0.2.0")  # plugin.json still says 0.1.0
    with pytest.raises(KitError, match="0.1.0"):
        snapshot(kit_repo, "v0.2.0", tmp_path / "home", run)

def test_latest_tag_is_semver_ordered(kit_repo):
    tag(kit_repo, "v0.10.0"); tag(kit_repo, "v0.9.0")
    assert latest_tag(kit_repo, run) == "v0.10.0"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_snapshot.py` — expect FAIL.
- [ ] **Step 3: Implement** (`tarfile` on the archive bytes; `tempfile.mkdtemp(dir=kit_home)`).
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(apply): immutable version snapshots"`.

### Task 10: Settings edits

Model: sonnet

**Files:**
- Create: `src/kit/settings_edit.py`
- Test: `tests/test_settings_edit.py`

**Interfaces:**
- Produces: `read_settings(repo) -> dict` (`{}` if missing; `KitError` on bad JSON, naming the file); `write_settings(repo, settings: dict) -> None` (indent 2, trailing newline); `with_kit(settings: dict, version: str, snapshot_path: Path) -> dict` (removes every `extraKnownMarketplaces` key matching `^kit-v\d+-\d+-\d+$` and every `enabledPlugins` key `kit@kit-v…`, then adds `extraKnownMarketplaces[marketplace_name(version)] = {"source": {"source": "directory", "path": str(snapshot_path)}}` and `enabledPlugins["kit@" + name] = true`); `without_hook_scripts(settings: dict, scripts: list[str]) -> tuple[dict, list[str]]` (drops hook entries whose `command` contains `.claude/hooks/<script>`, then empty matcher groups, empty events and an empty `hooks`; returns the removed commands); `with_permissions(settings, starter: dict) -> dict` (adds `permissions` only if the key is absent). None of them mutates its input.

- [ ] **Step 1: Write the failing tests.** Fixtures `DGI_SETTINGS` and `INVEST_SETTINGS` are copies, as Python dicts, of `../dividend-growth/.claude/settings.json` and `../investment/.claude/settings.json` (read them once while writing the test; do not read them at test time).

```python
def test_dgi_settings_lose_both_local_hooks_and_keep_the_rest():
    s, removed = without_hook_scripts(with_kit(DGI_SETTINGS, "v0.1.0", Path("/h/v0.1.0")), ["test-layer-guard.mjs", "context-warn.mjs"])
    assert "hooks" not in s and len(removed) == 3
    assert s["permissions"] == DGI_SETTINGS["permissions"] and s["enabledPlugins"]["ponytail@ponytail"] is True
    assert s["extraKnownMarketplaces"]["kit-v0-1-0"] == {"source": {"source": "directory", "path": "/h/v0.1.0"}}
    assert s["enabledPlugins"]["kit@kit-v0-1-0"] is True

def test_invest_keeps_its_guard_in_both_matchers():
    s, removed = without_hook_scripts(INVEST_SETTINGS, ["test-layer-guard.mjs", "context-warn.mjs"])
    commands = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert commands == ['node "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.mjs"'] * 2 and len(removed) == 1

def test_upgrade_replaces_the_old_version():
    s = with_kit(with_kit({}, "v0.1.0", Path("/h/v0.1.0")), "v0.2.0", Path("/h/v0.2.0"))
    assert list(s["extraKnownMarketplaces"]) == ["kit-v0-2-0"] and list(s["enabledPlugins"]) == ["kit@kit-v0-2-0"]

def test_inputs_are_not_mutated():
    before = copy.deepcopy(DGI_SETTINGS)
    with_kit(DGI_SETTINGS, "v0.1.0", Path("/h")); without_hook_scripts(DGI_SETTINGS, ["context-warn.mjs"])
    assert DGI_SETTINGS == before

def test_permissions_added_only_when_absent():
    assert with_permissions({}, {"allow": ["x"]}) == {"permissions": {"allow": ["x"]}}
    assert with_permissions(DGI_SETTINGS, {"allow": ["x"]})["permissions"] == DGI_SETTINGS["permissions"]

def test_bad_json_names_the_file(tmp_path):
    (tmp_path / ".claude").mkdir(); (tmp_path / ".claude/settings.json").write_text("{")
    with pytest.raises(KitError, match="settings.json"): read_settings(tmp_path)
```

- [ ] **Step 2: Run** — expect FAIL. **Step 3: Implement.** **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(apply): settings edits as JSON"`.

### Task 11: Detection

Model: sonnet

**Files:**
- Create: `src/kit/detect.py`
- Test: `tests/test_detect.py`

**Interfaces:**
- Produces: `Detected(package: str, test_command: str, pipeline_test: str, wiring_modules: tuple[str, ...], wiring_functions: tuple[str, ...], unresolved: tuple[str, ...])`; `detect(repo: Path) -> Detected`; `resolve(d: Detected, answers: dict[str, str], ask: Callable[[str, str], str] | None) -> Detected`; `test_layers_json(d: Detected) -> dict` (the task 3 config, `conventions_doc` = `docs/code-conventions.md`); `wiring_functions_from_guard(text: str) -> tuple[str, ...]`.

Rules:
- Stack: `pyproject.toml` and `uv.lock` both present, else `KitError("unsupported stack: no language pack for this repo (supported: python-uv)")`.
- `package`: module of the first `[project.scripts]` value (`"dgi.cli:app"` → `dgi`), else `project.name` with `-` → `_`.
- `test_command`: `uv run pytest -q` when `pytest` appears in `[dependency-groups]` or `[project.optional-dependencies]`, else unresolved `test_command`.
- `pipeline_test`: `tests/test_cli_pipeline.py` if it exists, else unresolved `pipeline_test`.
- `wiring_modules`: those of `cli`, `pipeline` present as `src/<package>/<m>.py` (or `<package>/<m>.py`).
- `wiring_functions`: from `.claude/hooks/test-layer-guard.mjs` if present, using `re.findall(r"\\b(\w+)\\s\*\\\(", text)`; else unresolved `wiring_functions`, with the `run_*` function names of the pipeline module (via `ast`) as the proposal shown by `ask`.
- `resolve`: `answers` keys `test_command`, `pipeline_test`, `wiring_functions` (comma-separated) override any value; each remaining unresolved key is asked with `ask(key, proposal)`; with `ask=None` and anything unresolved → `KitError` naming the flags `--test-command`, `--pipeline-test`, `--wiring-functions`.

- [ ] **Step 1: Write the failing tests** (helpers build repos shaped like dividend-growth and investment in `tmp_path`: `pyproject.toml`, `uv.lock`, `src/<pkg>/cli.py`, `src/<pkg>/pipeline.py` with `def run_refresh(` / `def run_all(` and one other `run_` function, `tests/test_cli_pipeline.py`, and a guard file holding the real WIRING line copied from each repo):

```python
def test_dgi_shape(dgi_repo):
    d = detect(dgi_repo)
    assert (d.package, d.test_command, d.pipeline_test, d.wiring_modules, d.wiring_functions, d.unresolved) == ("dgi", "uv run pytest -q", "tests/test_cli_pipeline.py", ("cli", "pipeline"), ("run_refresh",), ())

def test_invest_shape(invest_repo):
    assert detect(invest_repo).wiring_functions == ("run_all",)

def test_without_a_guard_the_wiring_functions_are_asked(dgi_repo):
    (dgi_repo / ".claude/hooks/test-layer-guard.mjs").unlink()
    d = detect(dgi_repo)
    assert d.unresolved == ("wiring_functions",)
    asked = {}
    r = resolve(d, {}, lambda key, proposal: asked.setdefault(key, proposal) and "run_refresh")
    assert asked["wiring_functions"] == "run_refresh,run_rescore" and r.wiring_functions == ("run_refresh",)
    with pytest.raises(KitError, match="--wiring-functions"): resolve(d, {}, None)

def test_answers_override_detection(dgi_repo):
    assert resolve(detect(dgi_repo), {"test_command": "true"}, None).test_command == "true"

def test_unsupported_stack(tmp_path):
    with pytest.raises(KitError, match="python-uv"): detect(tmp_path)
```

- [ ] **Step 2: Run** — expect FAIL. **Step 3: Implement** (`tomllib`, `ast`). **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(apply): deterministic detection for python-uv repos"`.

### Task 12: Migration by known content

Model: sonnet

**Files:**
- Create: `scripts/known_hashes.py`, `src/kit/known_hashes.json`, `src/kit/migrate.py`
- Test: `tests/test_migrate.py`

**Interfaces:**
- Produces: `CANDIDATES: tuple[str, ...]` = `.claude/agents/implementer-haiku.md`, `.claude/agents/implementer-sonnet.md`, `.claude/agents/reviewer-sonnet.md`, `.claude/hooks/test-layer-guard.mjs`, `.claude/hooks/context-warn.mjs`, `scripts/token_report.py`, `tests/test_token_report.py`, `tests/test_context_warn_hook.py`; `HOOK_SCRIPTS = ("test-layer-guard.mjs", "context-warn.mjs")`; `load_known(path: Path | None = None) -> dict[str, list[str]]` (default: packaged `known_hashes.json`); `Migration(remove: tuple[str, ...], overrides: tuple[str, ...])`; `plan_migration(repo, known) -> Migration` (candidate present and its SHA-256 in `known[path]` → remove; present otherwise → override; absent → neither); `apply_migration(repo, m) -> None`; `prose_mentions(repo: Path, run: Runner) -> list[str]` (`git grep -n -E 'implementer-haiku|implementer-sonnet|reviewer-sonnet|test-layer-guard|context-warn|token_report'` over tracked files outside `.claude/`, minus lines already containing `kit:` or `kit bench`; returns `"path:line"`; `git grep` exit 1 = none).
- `scripts/known_hashes.py <repo>...` prints the JSON map of `CANDIDATES` hashes found in the given repos (read-only), merged and sorted.

- [ ] **Step 1: Write the failing tests:**

```python
def test_known_file_is_removed_and_edited_one_kept(tmp_path):
    write(tmp_path, ".claude/agents/implementer-haiku.md", "stock"); write(tmp_path, ".claude/hooks/context-warn.mjs", "edited")
    known = {".claude/agents/implementer-haiku.md": [sha("stock")], ".claude/hooks/context-warn.mjs": [sha("stock")]}
    assert plan_migration(tmp_path, known) == Migration((".claude/agents/implementer-haiku.md",), (".claude/hooks/context-warn.mjs",))

def test_apply_migration_deletes_only_the_remove_list(tmp_path): ...
    # remove list file gone, override file still there

def test_prose_mentions_skip_lines_already_on_the_kit(git_repo):
    commit(git_repo, {"CLAUDE.md": "use implementer-haiku\nuse kit:implementer-haiku\n", ".claude/agents/x.md": "implementer-haiku"})
    assert prose_mentions(git_repo, run) == ["CLAUDE.md:1"]

def test_packaged_known_hashes_cover_dividend_growth_files():
    known = load_known()
    assert all(known.get(p) for p in CANDIDATES)
```

- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement** `migrate.py` and `scripts/known_hashes.py`, then generate the data: `uv run python scripts/known_hashes.py ../dividend-growth ../investment > src/kit/known_hashes.json` (reads only; run from the kit repo). Investment has no `reviewer-sonnet.md`, `context-warn.mjs` or `token_report.py`; dividend-growth supplies those.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(apply): migrate local copies by known content"`.

### Task 13: Verify

Model: sonnet

**Files:**
- Create: `src/kit/verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `parse_frontmatter` (task 2), `read_settings` (task 10).
- Produces: `Check(name: str, passed: bool, detail: str)`; `check_settings(repo) -> Check`; `check_guard(plugin: Path, repo: Path, layers: dict, run_input: RunInput) -> Check` (runs `node <plugin>/hooks/test-layer-guard.mjs` with `CLAUDE_PROJECT_DIR=repo`: `from <package>.<first module> import x` written to `tests/test_kit_probe.py` must be denied, and the same text written to `pipeline_test` must get `additionalContext`); `check_context_warn(plugin: Path, tmp: Path, run_input: RunInput) -> Check` (a one-call transcript under the step gives no output); `check_agents(plugin: Path) -> Check` (every agent has `name`, `description`, `model`, `tools`); `check_tests(repo: Path, test_command: str, run_input: RunInput) -> Check` (passed if the command exits 0; on failure `detail` = `"<command> failed; this may predate the kit: run it on the default branch to compare"`); `run_checks(...) -> list[Check]` in that order. These checks need stdin and env: extend `kit.gitrun` with `RunInput = Callable[[list[str], Path, str, dict[str, str]], subprocess.CompletedProcess[str]]` and `run_input(cmd, cwd, stdin, env)` (no raise; callers read `returncode`). `check_tests` runs the command through `sh -c`.

- [ ] **Step 1: Write the failing tests:** one pass and one fail per check. The guard checks use the real plugin dir from task 3 and a tmp repo with a `test-layers.json` (pass) or with `wiring_functions` for another package (fail: the probe is not denied); `check_tests` with commands `true` and `false`, asserting the fail detail contains "may predate the kit"; `check_agents` on a copy of `plugin/` with one agent's `tools:` line deleted fails and names the file; skip node-dependent tests without `node`.
- [ ] **Step 2: Run** — expect FAIL. **Step 3: Implement.** **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(apply): post-apply checks"`.

### Task 14: Git operations, `apply` wiring and CLI

Model: sonnet

**Files:**
- Create: `src/kit/gitops.py`, `src/kit/apply.py` (wiring)
- Modify: `src/kit/cli.py`
- Test: `tests/test_gitops.py`, `tests/test_cli_pipeline.py`

**Interfaces:**
- Consumes: tasks 6–13.
- Produces: `gitops.is_clean(repo, run) -> bool`; `gitops.create_branch(repo, name, run)`; `gitops.commit_all(repo, message, run) -> str` (sha); `gitops.commit_time(repo, sha, run) -> str` (UTC ISO); `gitops.open_pr(repo, title, body, run) -> str` (`gh pr create --title --body`, returns the URL line); `gitops.pr_body(version: str, m: Migration, removed_hooks: list[str], added: list[str], prose: list[str], checks: list[Check]) -> str` (sections "Added", "Removed (known kit content)", "Kept as local overrides", "Edit by hand on this branch" listing `prose`, "Checks"). `apply.apply(repo, version, kit_repo, kit_home, answers, ask, open_pr: bool, known: dict, root: Path, run) -> ApplyResult(branch, commit, pr_url | None, checks)`.

`apply` order (spec steps 1–7): fail with `KitError("uncommitted changes in <repo>")` unless clean; read `kit.json`, and `with_apply` early so a repeated version fails before any change; `create_branch("chore/claude-kit-<version>")`; on the first apply `write_baseline`; `detect` + `resolve`; `snapshot`; settings: `with_kit`, `without_hook_scripts(HOOK_SCRIPTS)` only for scripts the migration removes, `with_permissions(starter/permissions.json)`; write `.claude/test-layers.json`; `apply_migration`; copy each `starter/` file whose target is missing; `run_checks` — any failure raises `KitError` listing the failed checks and "branch <name> left for inspection; no PR"; commit; record `Apply(version, commit, commit_time, overrides)` with `write_kitfile`; commit again (`chore: record claude-kit <version>`); `prose_mentions`; `open_pr` unless `open_pr` is false.

- [ ] **Step 1: Write the failing tests.**
  - UNIT `test_gitops.py`: `is_clean` true/false on a temp repo; `pr_body` lists an override and a prose line under their headings.
  - PIPELINE in `tests/test_cli_pipeline.py` (fixture: a dgi-shaped temp git repo from task 11's helper, committed, with the two local hook files and their settings entries; a kit repo tagged `v0.1.0` built from this repo's `plugin/` and `starter/`; a `--known-hashes` file with the fixture files' hashes; `--test-command true`; `--no-pr`; `--kit-home` and `--root` in `tmp_path`):
    1. `main(["apply", repo, "--version", "v0.1.0", ...]) == 0`; the branch is `chore/claude-kit-v0.1.0`; `kit.json` has one apply with a 40-char commit; `settings.json` names `kit@kit-v0-1-0`; the local hook files are gone; `.claude/kit-bench/baseline.json` exists.
    2. Running it again exits 1 with `error: already on v0.1.0` and adds no commit.
    3. A dirty repo exits 1 with `error: uncommitted changes`.
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement** `gitops.py`, `apply.py`, and `kit apply <repo> [--version] [--test-command] [--pipeline-test] [--wiring-functions] [--no-pr] [--kit-home] [--known-hashes] [--root]` (the last three default to `~/.claude/kit`, the packaged file and `~/.claude/projects`; `ask` uses `input()` when stdin is a TTY, else `None`; the kit repo is the one `kit` runs from, found via `Path(kit.__file__).parents[2]`).
- [ ] **Step 4: Run** `uv run pytest` — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: kit apply command"`.

After task 14: final whole-branch review on Opus (plan index, "Execution notes").
