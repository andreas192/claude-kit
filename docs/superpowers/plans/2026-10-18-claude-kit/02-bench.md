# Phase 2: `kit bench` and `kit status` (tasks 4–8)

Index and global constraints: `../2026-10-18-claude-kit.md`. Measures and their transcript fields: spec, "Builder decisions", "Measures the transcripts support".

### Task 4: Port `token_report.py` into `kit.bench`

Model: sonnet

**Files:**
- Create: `src/kit/bench/__init__.py`, `src/kit/bench/transcripts.py`, `src/kit/bench/benchmarks.py`
- Test: `tests/test_transcripts.py`, `tests/test_benchmarks.py`

**Interfaces:**
- Produces, in `transcripts.py`: `Call`, `Transcript`, `Subagent`, `Session` (as in `../dividend-growth/scripts/token_report.py`), plus `Transcript.end: str` (last timestamp seen); `parse_transcript(lines: Iterable[str]) -> Transcript`; `load_sessions(project_dir: Path) -> list[Session]`; `transcript_dir_name(repo: Path) -> str`; `main_checkout(repo: Path) -> Path`; `project_dirs(root: Path, repo: Path) -> list[Path]`; `agent_kind(agent_type: str) -> str` (drops a `plugin:` prefix: `"kit:implementer-haiku"` → `"implementer-haiku"`).
- Produces, in `benchmarks.py`: `Benchmark(key, label, target, measure)`, `BENCHMARKS` (B1–B13 unchanged), `is_implementer`, `is_reviewer`, `is_search`, `task_count`, `session_cost`, `cost_per_task`, `fmt(value: float) -> str`. The classifiers call `agent_kind` first.

- [ ] **Step 1: Write the failing tests.** Copy `../dividend-growth/tests/test_token_report.py` and split it by module: parsing tests into `test_transcripts.py` (import from `kit.bench.transcripts`), measure tests into `test_benchmarks.py`. Drop the `importlib` loader. Add:

```python
def test_end_is_the_last_timestamp():
    t = parse_transcript([rec("2026-10-17T07:00:00Z"), assistant("a"), rec("2026-10-17T08:30:00Z")])
    assert (t.start, t.end) == ("2026-10-17T07:00:00Z", "2026-10-17T08:30:00Z")

def test_agent_kind_drops_the_plugin_prefix():
    assert [agent_kind(a) for a in ("kit:implementer-haiku", "implementer-haiku", "Explore")] == ["implementer-haiku", "implementer-haiku", "Explore"]

def test_plugin_agents_are_classified_like_local_ones():
    agent = Subagent("kit:reviewer-sonnet", "Review batch 2", Transcript())
    assert is_reviewer(agent) and not is_implementer(agent)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_transcripts.py tests/test_benchmarks.py` — expect FAIL.
- [ ] **Step 3: Implement** by moving the code from `token_report.py` (without `main`, `parse_args`, `split_sessions`, `in_window`, `benchmark_table`, `session_lines`, `task_lines`); add `end` and `agent_kind`.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(bench): port token_report transcripts and B1-B13"`.

### Task 5: Friction, quality and speed measures from transcripts

Model: sonnet

**Files:**
- Modify: `src/kit/bench/transcripts.py` (new `Transcript` fields, `parse_transcript(lines, test_command: str = "")`, `load_sessions(project_dir, test_command="")`)
- Create: `src/kit/bench/measures.py`
- Test: `tests/test_transcripts.py`, `tests/test_measures.py`

**Interfaces:**
- Produces: `Transcript` fields `permission_denials: int`, `hook_denials: int`, `context_warnings: int`, `failed_test_runs: int`, `last_text: str` (text blocks of the last assistant message). `measures.MEASURES: list[Benchmark]` with keys and labels:
  `F1` permission denials per session, `F2` hook denials per session, `F3` context-warn firings per session, `Q1` reviewer findings per reviewer, `Q2` re-reviews per implementer, `Q3` failed test runs per implemented task, `S1` session duration, median (min), `S2` owner prompts per implemented task. `measures.NOT_MEASURED: list[str] = ["permission prompts: approved prompts are not recorded in transcripts"]`.

Patterns (module constants in `transcripts.py`): `PERMISSION_DENIED = re.compile(r"^Permission for this action was denied|doesn't want to proceed")`, `HOOK_DENIED = re.compile(r"^\w+:\w+ hook error:")`, `CONTEXT_WARN = "Context is "` on `attachment` records of type `hook_system_message` or `hook_additional_context` (content a string or a list of strings). A failed test run is a `tool_result` with `is_error: true` whose `tool_use_id` belongs to a `Bash` `tool_use` whose `command` contains `test_command` (empty `test_command` counts none). In `measures.py`: `FINDING = re.compile(r"^\s*\d+\.\s", re.M)`, `RE_REVIEW = re.compile(r"re-?review", re.I)`; a reviewer whose `last_text` starts with `PASS` has 0 findings.

- [ ] **Step 1: Write the failing tests.** In `test_transcripts.py`, builders `tool_use(id, command)`, `tool_result(id, text, error)`, `attachment(kind, content)`:

```python
def test_counts_denials_and_context_warnings():
    t = parse_transcript([
        tool_result("1", "Permission for this action was denied by the Claude Code auto mode classifier.", True),
        tool_result("2", "The user doesn't want to proceed with this tool use.", True),
        tool_result("3", "PreToolUse:Bash hook error: This may change ../capital-trading", True),
        tool_result("4", "Exit code 1", True),
        attachment("hook_system_message", "Context is 87k tokens (checkpoint: 80k)."),
        attachment("hook_additional_context", ["Context is 84k tokens, past the 80k checkpoint."]),
        attachment("hook_additional_context", ["Follow docs/code-conventions.md section 3"]),
    ])
    assert (t.permission_denials, t.hook_denials, t.context_warnings) == (2, 1, 2)

def test_failed_test_runs_match_the_test_command_only():
    lines = [tool_use("a", "uv run pytest -q tests/x.py"), tool_result("a", "1 failed", True),
             tool_use("b", "uv run pytest -q tests/x.py"), tool_result("b", "1 passed", False),
             tool_use("c", "ls nope"), tool_result("c", "Exit code 1", True)]
    assert parse_transcript(lines, "uv run pytest").failed_test_runs == 1
    assert parse_transcript(lines).failed_test_runs == 0

def test_last_text_is_the_final_assistant_text():
    assert parse_transcript([assistant_text("m1", "draft"), assistant_text("m2", "PASS")]).last_text == "PASS"
```

  In `test_measures.py`, sessions built from `Transcript` objects directly:

```python
def test_reviewer_findings_count_numbered_lines_and_pass_is_zero():
    s = session(subagents=[reviewer("Review batch 1", "1. a.py:3 x\n2. b.py:9 y"), reviewer("Review batch 2", "PASS")])
    assert measure("Q1", [s]) == 1.0

def test_rereviews_per_implementer():
    s = session(subagents=[implementer("Tasks 1-2"), implementer("Task 3"), reviewer("Re-review batch 1", "PASS")])
    assert measure("Q2", [s]) == 0.5

def test_duration_is_median_minutes():
    assert measure("S1", [session(start="2026-10-17T07:00:00Z", end="2026-10-17T07:30:00Z")]) == 30.0

def test_not_measured_names_permission_prompts():
    assert any(x.startswith("permission prompts") for x in NOT_MEASURED)
```

  (`measure(key, sessions)` is a test helper that looks the key up in `MEASURES`.) Q3 and S2 divide by the implemented tasks of sessions with at least one implementer (`task_count` over implementer descriptions), NaN when there are none; add one test each with 2 tasks and 3 failed runs → 1.5, and 4 prompts → 2.0.
- [ ] **Step 2: Run** both files — expect FAIL.
- [ ] **Step 3: Implement** the fields in `count_user_record` / a new `count_attachment` and the tool-use map in `parse_transcript`; the measures as small functions in `measures.py` registered in `MEASURES`.
- [ ] **Step 4: Run** — expect PASS, and the task 4 tests still pass.
- [ ] **Step 5: Commit** `git commit -am "feat(bench): friction, quality and speed measures"` (add `measures.py`).

### Task 6: Fixes within 7 days, from git

Model: sonnet

**Files:**
- Create: `src/kit/gitrun.py`, `src/kit/bench/gitlog.py`
- Test: `tests/test_gitlog.py`

**Interfaces:**
- Produces: `kit.gitrun.Runner = Callable[[list[str], Path], str]`; `kit.gitrun.run(cmd: list[str], cwd: Path) -> str` (subprocess, text, raises `KitError("<cmd> failed: <stderr first line>")` on non-zero). In `gitlog.py`: `Merge(sha: str, time: str, subject: str, files: frozenset[str])`; `default_branch(repo, run) -> str` (`git symbolic-ref --short refs/remotes/origin/HEAD` without `origin/`, else `main`); `merges(repo, branch, run) -> list[Merge]` (first-parent history, oldest first, files diffed against the first parent: `git log --first-parent -m --reverse --name-only --format=%x00%H%x09%cI%x09%s <branch>`); `followed_by_fix(merges, days=FIX_WINDOW_DAYS) -> list[bool]` (per merge: a later merge within `days` whose subject matches `FIX = re.compile(r"\b(fix|revert)", re.I)` and shares a file); `merged_at(repo, version, branch, run) -> str | None` (committer time of the oldest first-parent commit on `branch` whose `.claude/kit.json` contains `"version": "<version>"`, via `git log --first-parent --reverse --format=%cI -S'"version": "<version>"' <branch> -- .claude/kit.json`).

- [ ] **Step 1: Write the failing tests** on a temp git repo built in code (helper `commit(repo, files: dict[str, str], message, date)` with `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`, and `merge_branch(repo, name, files, subject, date)` doing `checkout -b`, commit, `checkout main`, `merge --no-ff -m subject`):

```python
def test_merges_list_files_against_first_parent(repo):
    merge_branch(repo, "feat/a", {"a.py": "1"}, "Merge pull request #1 from x/feat/a", "2026-10-01T10:00:00Z")
    [m] = [m for m in merges(repo, "main", run) if m.subject.startswith("Merge")]
    assert m.files == {"a.py"}

def test_fix_within_window_on_same_file_counts():
    ms = [Merge("1", "2026-10-01T10:00:00Z", "feat a", frozenset({"a.py"})),
          Merge("2", "2026-10-05T10:00:00Z", "Merge pull request #2 from x/fix/a", frozenset({"a.py"})),
          Merge("3", "2026-10-20T10:00:00Z", "fix: b", frozenset({"a.py"}))]
    assert followed_by_fix(ms) == [True, False, False]

def test_merged_at_finds_the_merge_that_brought_the_entry(repo):
    merge_branch(repo, "chore/claude-kit-v0.1.0", {".claude/kit.json": '{"applies": [{"version": "v0.1.0"}]}'}, "Merge kit", "2026-10-02T09:00:00Z")
    assert merged_at(repo, "v0.1.0", "main", run) == "2026-10-02T09:00:00+00:00"
    assert merged_at(repo, "v0.2.0", "main", run) is None
```

- [ ] **Step 2: Run** `uv run pytest tests/test_gitlog.py` — expect FAIL.
- [ ] **Step 3: Implement** `gitrun.py` and `gitlog.py`. Times compare as parsed `datetime`s (normalize `Z`).
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(bench): git merges and fix-within-7-days"`.

### Task 7: `.claude/kit.json`, windows and the report table

Model: sonnet

**Files:**
- Create: `src/kit/kitfile.py`, `src/kit/bench/windows.py`, `src/kit/bench/report.py`
- Test: `tests/test_kitfile.py`, `tests/test_windows.py`, `tests/test_report.py`

**Interfaces:**
- Produces, in `kitfile.py`: `Apply(version: str, commit: str, applied_at: str, overrides: tuple[str, ...] = ())`; `KitFile(test_command: str, applies: tuple[Apply, ...])`; `read_kitfile(repo: Path) -> KitFile | None`; `with_apply(kit: KitFile, apply: Apply) -> KitFile` (appends; `KitError("already on <version>")` if the last apply has the same version); `write_kitfile(repo: Path, kit: KitFile) -> None` (JSON, indent 2, keys `test_command`, `applies`, trailing newline).
- Produces, in `windows.py`: `Window(name: str, start: str, end: str)` (ISO UTC strings, `""` = open); `make_windows(times: list[tuple[str, str]]) -> list[Window]` (input `(version, effective time)` in apply order; output `pre-kit` then one per version); `assign(sessions, windows) -> dict[str, list[Session]]` (by `session.main.start`; sessions with no start dropped).
- Produces, in `report.py`: `Column(name: str, sessions: list[Session])`; `report_lines(columns: list[Column], control: list[Column] | None, measures: list[Benchmark], not_measured: list[str], min_sessions: int = MIN_SESSIONS) -> list[str]` (a markdown table).

Table layout: header `| measure | <w1> | <w2> | Δ <w1>→<w2> | control Δ <w1>→<w2> | ... | target |`, a `sessions` row, then one row per measure. A Δ is later minus earlier, formatted with `fmt`; a Δ cell says `not enough data` when either window has fewer than `min_sessions` sessions (control Δ uses the control's own counts); control columns appear only when `control` is given. After the table: `Not measured:` and one bullet per `not_measured` entry.

- [ ] **Step 1: Write the failing tests.**

```python
def test_with_apply_appends_and_refuses_the_same_version():
    k = with_apply(KitFile("uv run pytest -q", ()), Apply("v0.1.0", "abc", "2026-10-18T10:00:00Z"))
    assert [a.version for a in k.applies] == ["v0.1.0"]
    with pytest.raises(KitError, match="already on v0.1.0"):
        with_apply(k, Apply("v0.1.0", "def", "2026-10-19T10:00:00Z"))

def test_kitfile_round_trip(tmp_path):
    k = KitFile("t", (Apply("v0.1.0", "abc", "2026-10-18T10:00:00Z", ("x.md",)),))
    write_kitfile(tmp_path, k)
    assert read_kitfile(tmp_path) == k and read_kitfile(tmp_path / "none") is None

def test_windows_and_assignment_by_first_record():
    ws = make_windows([("v0.1.0", "2026-10-18T00:00:00Z"), ("v0.2.0", "2026-10-25T00:00:00Z")])
    assert [(w.name, w.start, w.end) for w in ws] == [("pre-kit", "", "2026-10-18T00:00:00Z"), ("v0.1.0", "2026-10-18T00:00:00Z", "2026-10-25T00:00:00Z"), ("v0.2.0", "2026-10-25T00:00:00Z", "")]
    spanning = session(start="2026-10-17T23:00:00Z", end="2026-10-18T02:00:00Z")
    assert assign([spanning, session(start="")], ws)["pre-kit"] == [spanning]

def test_delta_needs_min_sessions_on_both_sides():
    lines = report_lines([Column("pre-kit", sessions(6)), Column("v0.1.0", sessions(4))], None, [FIXED_MEASURE], [], 5)
    assert "not enough data" in row(lines, FIXED_MEASURE.key)

def test_control_delta_column_and_not_measured():
    lines = report_lines([Column("pre-kit", sessions(5)), Column("v0.1.0", sessions(5))], [Column("pre-kit", sessions(5)), Column("v0.1.0", sessions(5))], [FIXED_MEASURE], ["permission prompts: x"], 5)
    assert "control Δ pre-kit→v0.1.0" in lines[0] and lines[-1] == "- permission prompts: x"
```

  (`FIXED_MEASURE` returns `len(sessions)`, so the Δ in the second test is `0.00`; assert that cell too.)
- [ ] **Step 2: Run** the three files — expect FAIL.
- [ ] **Step 3: Implement** the three modules. `MIN_SESSIONS = 5` lives in `report.py`.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(bench): kit.json, version windows and report table"`.

### Task 8: `kit bench`, baseline and `kit status`

Model: sonnet

**Files:**
- Create: `src/kit/bench/run.py` (wiring), `src/kit/status.py`
- Modify: `src/kit/cli.py`
- Test: `tests/test_status.py`, `tests/test_bench_values.py`, `tests/test_cli_pipeline.py`

**Interfaces:**
- Consumes: tasks 4–7.
- Produces: `bench.run.run_bench(repo: Path, control: Path | None, root: Path, today: date, run: Runner) -> Path` (loads sessions of the repo and its worktrees with the repo's `test_command`, builds windows from `kit.json` with `merged_at` falling back to `applied_at`, the same windows for the control, writes `.claude/kit-bench/<today>.md`, returns its path; a repo without `kit.json` gets one `pre-kit` column); `bench.run.baseline_values(sessions: list[Session]) -> dict[str, float]` (every B, F, Q, S key → value, NaN as `null`); `bench.run.write_baseline(repo, root, run) -> Path` (`.claude/kit-bench/baseline.json`, all sessions so far). Q4 "share of merges followed by a fix within 7 days" is added to the report as a row computed from `gitlog` per window (merges whose time falls in the window). `status.RepoStatus(name: str, version: str, overrides: tuple[str, ...])`; `status.find_kit_repos(base: Path) -> list[RepoStatus]` (direct children with `.claude/kit.json`, sorted by name, version and overrides of the last apply). `bench.run.default_control(repo: Path) -> Path | None` (the first other repo from `find_kit_repos(repo.parent)`, else None). CLI: `kit bench <repo> [--control <repo>] [--since <ISO UTC>] [--root <dir>]` (`--since` drops sessions that start earlier; no `--control` → `default_control`), `kit status [--base <dir>]` (default `~/Projects/Personal`), printing lines.

- [ ] **Step 1: Write the failing tests.**
  - UNIT `test_status.py`: two child dirs, one with `kit.json` (last apply `v0.2.0`, overrides `(".claude/agents/x.md",)`) → `[RepoStatus("a", "v0.2.0", (".claude/agents/x.md",))]`.
  - UNIT `test_bench_values.py`: `baseline_values` on two built sessions has keys `B1`…`B13`, `F1`…`F3`, `Q1`…`Q3`, `S1`, `S2`; a NaN measure serializes as `null` through `json.dumps`.
  - PIPELINE `test_cli_pipeline.py` (fixture: temp git repo with `kit.json` applied `2026-10-18T00:00:00Z`, and a temp transcript root holding 6 sessions before and 5 after in `<root>/<transcript_dir_name(repo)>/`):
    1. `main(["bench", str(repo), "--root", str(root)]) == 0`, the printed table has columns `pre-kit` and `v0.1.0` and one numeric Δ cell in row `B1`, and `.claude/kit-bench/<today>.md` exists.
    2. Running it twice leaves the same file content.
    3. `main(["bench", str(tmp_path / "missing")])` returns 1 with `error:` on stderr.
  - UNIT `test_status.py` also: `default_control` returns the sibling kit repo and None when the repo is the only one.
- [ ] **Step 2: Run** the three files — expect FAIL.
- [ ] **Step 3: Implement** `run.py` (wiring only: no branches beyond "no kit.json"), `status.py`, the CLI subcommands.
- [ ] **Step 4: Run** `uv run pytest` (full suite) — expect PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: kit bench, baseline and kit status commands"`.
