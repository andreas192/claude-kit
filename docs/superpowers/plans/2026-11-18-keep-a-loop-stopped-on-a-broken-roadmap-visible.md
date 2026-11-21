# Keep a Loop Stopped on a Broken Roadmap Visible Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A loop run that stops on `env` through `_Run.failed` leaves `env-failure.txt` in the runtime dir, `kit loop status` and `kit roadmap` lead with `loop stopped since <time>: <reason>` while it exists, and the next run that gets past the environment checks deletes it.

**Architecture:** `src/kit/loop/alert.py` gets a second record file next to `probe-failure.txt`, sharing the read/record/clear code, plus `alert_lines(runtime)` that both readers use. `_Run.failed` in `src/kit/loop/driver.py` takes a second, kit-written-only reason and records it when it returns `env`; a new `_Run.passed()` replaces every `self.errors = 0` and also clears the record. `status_lines` and `format_report` take the list of alert lines.

**Tech Stack:** Python 3, pytest, `uv run pytest -q`.

**Spec:** `docs/superpowers/specs/2026-11-18-keep-a-loop-stopped-on-a-broken-roadmap-visible-design.md`

## Global Constraints

- Runtime dir is `~/.claude/kit/loop/<repo>/` (`env.runtime`); the new file is `env-failure.txt`, one line `<first time> <latest reason>`, time as `when.isoformat(timespec="seconds")`.
- Shown line: `loop stopped since <time>: <reason>`. The probe line `loop probe failing since <time>: <reason>` and `probe-failure.txt` stay byte-for-byte as today.
- The recorded reason holds only kit-written text, never session text or stderr.
- No change to `MAX_ERRORS = 2`, the banner (one per `env` stop, full `why`), exit codes, `guarded`, `pick_only`, the probe path, or the cross-repo `kit status`.
- `pick_only` (`kit loop run --pick-only`) neither writes nor clears the file.
- Tests offline, fixtures in code; follow `docs/code-conventions.md` (UNIT tests beside each module, PIPELINE only in `tests/test_cli_pipeline.py`).
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. The runtime dir cannot be written when `failed` records (e.g. `env-failure.txt` is a directory): the run must still return `env` with one banner and log the write error, not crash. Test in Task 2.
2. An `OSError` with no `cmd` (e.g. `FileNotFoundError` from launching `git`): the reason is `OSError: FileNotFoundError`, with no filename or message. Test in Task 2.
3. A `session failed:` detail with newlines or a long result: recorded as just `<stage> stage: session failed`. Test in Task 2 (redaction unit test).
4. A blank or whitespace-only record file (interrupted write): reads as no record, so no `loop stopped since : ` line. Test in Task 1.
5. A clear that fails (`OSError` from `unlink`) in `passed()`: logged, the run goes on. Test in Task 2.

---

### Task 1: Env-failure record in `alert.py` ✅ done (b867f8d)

**Model:** haiku

**Files:**
- Modify: `src/kit/loop/alert.py`
- Test: `tests/test_loop_alert.py`

**Interfaces:**
- Produces:
  - `ENV_FAILURE_FILE = "env-failure.txt"`
  - `record_env_failure(runtime: Path, when: datetime, why: str) -> None`
  - `clear_env_failure(runtime: Path) -> None`
  - `env_failure_line(runtime: Path) -> str` — `loop stopped since <time>: <reason>` or `""`
  - `alert_lines(runtime: Path) -> list[str]` — probe line, then env line, each only when non-empty
  - Unchanged: `record_probe_failure`, `clear_probe_failure`, `probe_failure_line`, `PROBE_FAILURE_FILE`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_loop_alert.py`; keep the probe tests as they are; reuse its `FIRST`/`LATER` constants)

```python
def test_no_env_record_is_no_line(tmp_path):
    assert env_failure_line(tmp_path) == ""

def test_env_record_keeps_the_first_time_and_the_latest_reason(tmp_path):
    record_env_failure(tmp_path, FIRST, "roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked")
    record_env_failure(tmp_path, LATER, "git fetch origin failed (exit 1)")
    assert env_failure_line(tmp_path) == "loop stopped since 2026-11-03T15:00:05: git fetch origin failed (exit 1)"

def test_env_record_reason_is_one_line(tmp_path):
    record_env_failure(tmp_path, FIRST, "spec stage:\n  session failed\n")
    assert env_failure_line(tmp_path).endswith(": spec stage: session failed")

def test_env_record_creates_a_missing_runtime_dir(tmp_path):
    record_env_failure(tmp_path / "new", FIRST, "why")
    assert env_failure_line(tmp_path / "new") != ""

def test_env_clear_is_idempotent(tmp_path):
    record_env_failure(tmp_path, FIRST, "why")
    clear_env_failure(tmp_path)
    clear_env_failure(tmp_path)
    assert env_failure_line(tmp_path) == ""

def test_a_blank_record_file_reads_as_no_record(tmp_path):
    (tmp_path / ENV_FAILURE_FILE).write_text("  \n")
    assert env_failure_line(tmp_path) == "" and alert_lines(tmp_path) == []

def test_alert_lines_put_the_probe_before_the_env_stop_and_skip_absent_ones(tmp_path):
    assert alert_lines(tmp_path) == []
    record_env_failure(tmp_path, FIRST, "env why")
    assert alert_lines(tmp_path) == ["loop stopped since 2026-11-03T15:00:05: env why"]
    record_probe_failure(tmp_path, FIRST, "probe why")
    assert alert_lines(tmp_path) == [
        "loop probe failing since 2026-11-03T15:00:05: probe why",
        "loop stopped since 2026-11-03T15:00:05: env why",
    ]
```

(Check `FIRST` in the file: the expected `2026-11-03T15:00:05` must match it; adjust the literal if `FIRST` differs.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_loop_alert.py -q`
Expected: FAIL with ImportError on `record_env_failure`.

- [ ] **Step 3: Implement in `src/kit/loop/alert.py`**

Make `_read(runtime: Path, name: str) -> tuple[str, str] | None` (returns `None` when the file is missing or its stripped text is empty), `_record(runtime: Path, name: str, when: datetime, why: str) -> None` (the current record body) and `_clear(runtime, name)`. The probe functions and the new env functions are one-line wrappers over them. Update the module docstring to name both records.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_loop_alert.py -q`
Expected: all pass, the existing probe tests included.

- [ ] **Step 5: Commit**

```bash
git add src/kit/loop/alert.py tests/test_loop_alert.py
git commit -m "feat(loop): env-failure record and alert_lines"
```

---

### Task 2: Record in `_Run.failed`, clear in `_Run.passed`

**Model:** sonnet

**Files:**
- Modify: `src/kit/loop/driver.py` (`_Run.failed`, `_Run.pick`, `_Run.work`, `_run_until_stop`, new helpers)
- Test: `tests/test_loop_driver.py`

**Interfaces:**
- Consumes: `record_env_failure`, `clear_env_failure`, `env_failure_line` from Task 1.
- Produces (module-level in `driver.py`, importable by tests):
  - `kit_detail(detail: str) -> str` — `"session failed"` when `detail` starts with `"session failed"`, else `detail` unchanged.
  - `command_reason(e: subprocess.CalledProcessError | OSError) -> str` — for `CalledProcessError`: `"<first 3 words of cmd> failed (exit <returncode>)"` (e.g. `git fetch origin failed (exit 1)`); for any other `OSError`: `"<first 3 words of cmd, or 'OSError'>: <type(e).__name__>"`. Never stderr, never `str(e)`. Only the first three words, so a `gh pr edit ... --body <text>` never reaches the record.
  - `_Run.failed(self, why: str, shown: str) -> str | None`
  - `_Run.passed(self) -> None`

- [ ] **Step 1: Write the failing tests** (append at the end of `tests/test_loop_driver.py`, after `bad_probe`, which they use; import `env_failure_line`, `record_env_failure` from `kit.loop.alert` and `command_reason`, `kit_detail` from `kit.loop.driver`)

```python
BROKEN = "### A\n- Status: soon\n"

def env_line(tmp_path) -> str:
    return env_failure_line(tmp_path / "runtime")

def test_kit_detail_drops_session_text_and_keeps_kit_details():
    assert kit_detail("session failed: secret\nmore") == "session failed"
    for d in ("stage made no commit", "pr stage reported ok but no ready PR exists", "no result line"):
        assert kit_detail(d) == d

def test_command_reason_names_the_command_and_exit_code_only():
    e = subprocess.CalledProcessError(1, ["gh", "pr", "edit", "3", "--body", "secret"], stderr="boom")
    assert command_reason(e) == "gh pr edit failed (exit 1)"
    assert command_reason(FileNotFoundError(2, "No such file", "git")) == "OSError: FileNotFoundError"

def test_a_broken_roadmap_on_two_runs_keeps_the_first_time(tmp_path):
    run(FakeEnv(tmp_path, scripts(), roadmap=BROKEN, now=lambda: datetime(2026, 10, 23, 10)).env())
    run(FakeEnv(tmp_path, scripts(), roadmap=BROKEN, now=lambda: datetime(2026, 10, 23, 15)).env())
    line = env_line(tmp_path)
    assert line.startswith("loop stopped since 2026-10-23T10:00:00: roadmap: docs/roadmap.md:1:")

def test_a_later_run_that_picks_clears_the_record(tmp_path):
    run(FakeEnv(tmp_path, scripts(), roadmap=BROKEN).env())
    run_fake(tmp_path, spec=[step()], plan=[step("LOOP: park x")])
    assert env_line(tmp_path) == ""

def test_a_later_run_with_nothing_left_clears_the_record(tmp_path):
    run(FakeEnv(tmp_path, scripts(), roadmap=BROKEN).env())
    assert run(FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER).env()) == "done"
    assert env_line(tmp_path) == ""

def test_a_run_on_an_unchanged_none_key_clears_the_record(tmp_path):
    run(FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER).env())
    record_env_failure(tmp_path / "runtime", FRIDAY, "git fetch origin failed (exit 1)")
    again = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    assert run(again.env()) == "done" and not any(c[:2] == ["git", "show"] for c in again.cmds)
    assert env_line(tmp_path) == ""

def test_a_resumed_branch_whose_first_stage_ends_ok_clears_the_record(tmp_path):
    keep = lambda f: record_env_failure(tmp_path / "runtime", FRIDAY, "git fetch origin failed (exit 1)")
    reason, f = run_fake(tmp_path, resume_branch="loop/a", setup=keep, build=[step()])
    assert reason == "done" and f.stages[:2] == ["probe", "build"]
    assert env_line(tmp_path) == ""

def test_a_resumed_branch_whose_stage_errors_twice_keeps_the_first_time(tmp_path):
    keep = lambda f: record_env_failure(tmp_path / "runtime", FRIDAY, "git fetch origin failed (exit 1)")
    reason, _ = run_fake(tmp_path, resume_branch="loop/a", setup=keep, build=[fail_step(), fail_step()])
    assert reason == "env"
    assert env_line(tmp_path) == "loop stopped since 2026-10-23T10:00:00: build stage: session failed"

def test_weekend_usage_limit_and_failed_probe_runs_keep_the_record(tmp_path):
    run(FakeEnv(tmp_path, scripts(), roadmap=BROKEN).env())
    assert run(FakeEnv(tmp_path, {}, now=lambda: SUNDAY).env()) == "weekend"
    assert run(FakeEnv(tmp_path, {"probe": [usage_step()]}).env()) == "limit"
    assert run(FakeEnv(tmp_path, {"probe": [bad_probe()]}).env()) == "env"
    assert "roadmap: docs/roadmap.md:1:" in env_line(tmp_path)

def test_two_stage_errors_record_session_failed_without_the_session_text(tmp_path):
    reason, f = run_fake(tmp_path, spec=[fail_step(), fail_step()])
    assert reason == "env" and env_line(tmp_path).endswith(": spec stage: session failed")
    assert "boom" not in (tmp_path / "runtime" / "env-failure.txt").read_text()
    assert any("boom" in n for n in f.notices)  # the banner still carries the full why

def test_two_git_failures_record_the_command_and_exit_code_without_stderr(tmp_path):
    f = FakeEnv(tmp_path, scripts())
    env = f.env()
    real = env.sh

    def always_fail(cmd):
        if cmd[:2] == ["git", "fetch"]:
            raise subprocess.CalledProcessError(1, cmd, stderr="down")
        return real(cmd)

    env.sh = always_fail
    assert run(env) == "env"
    assert env_line(tmp_path).endswith(": git fetch origin failed (exit 1)")
    assert "down" not in (tmp_path / "runtime" / "env-failure.txt").read_text()

def test_one_failure_then_success_in_one_run_writes_nothing(tmp_path):
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    f.fail_on = "git fetch"
    assert run(f.env()) == "done" and not (tmp_path / "runtime" / "env-failure.txt").exists()

def test_pick_only_on_a_broken_roadmap_writes_nothing(tmp_path):
    assert pick_only(FakeEnv(tmp_path, scripts(), roadmap=BROKEN).env()) == "env"
    assert not (tmp_path / "runtime" / "env-failure.txt").exists()

def test_pick_only_keeps_an_existing_record(tmp_path):
    record_env_failure(tmp_path / "runtime", FRIDAY, "why")
    assert pick_only(FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_A_OPEN).env()) == "done"
    assert env_line(tmp_path) != ""

def test_an_unwritable_record_still_stops_on_env_with_one_banner(tmp_path):
    (tmp_path / "runtime" / "env-failure.txt").mkdir(parents=True)  # write_text and unlink both raise OSError
    f = FakeEnv(tmp_path, scripts(), roadmap=BROKEN)
    assert run(f.env()) == "env" and len(f.notices) == 1
    assert any("could not write env-failure.txt" in m for m in f.logs)


def test_a_clear_that_fails_is_logged_and_the_run_goes_on(tmp_path):
    (tmp_path / "runtime" / "env-failure.txt").mkdir(parents=True)
    f = FakeEnv(tmp_path, scripts(), roadmap=ROADMAP_OWNER)
    assert run(f.env()) == "done" and any("could not clear env-failure.txt" in m for m in f.logs)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_loop_driver.py -q`
Expected: FAIL with ImportError on `kit_detail`.

- [ ] **Step 3: Implement in `src/kit/loop/driver.py`**

- Add `kit_detail` and `command_reason` per Interfaces.
- `_Run.failed(why, shown)`: unchanged log and banner with `why`; just before `return "env"`, call `record_env_failure(self.env.runtime, self.env.now(), shown)` inside `try/except OSError as e`, logging `could not write env-failure.txt: <_one_line(e)>` on failure.
- `_Run.passed()`: `self.errors = 0`, then `clear_env_failure(self.env.runtime)` in `try/except OSError`, logging `could not clear env-failure.txt: <_one_line(e)>`.
- Call sites:
  - `pick`, `RoadmapError`: `why = f"roadmap: {str(e).splitlines()[0]}"`; `return self.failed(why, why)`.
  - `pick`, unchanged `none_key`: call `self.passed()` before `return "done"`.
  - `pick`, `picked.item is None`: call `self.passed()` before `nothing_left`.
  - `pick`, replace `self.errors = 0` with `self.passed()`.
  - `work`: `self.failed(f"{stage} stage: {r.detail}", f"{stage} stage: {kit_detail(r.detail)}")`; replace `self.errors = 0` with `self.passed()`.
  - `_run_until_stop`: `loop.failed(<the existing why expression>, command_reason(e))`.
  - `once`, `unfinished` path: no new call. It skips `pick`, so the `passed()` in `work` after its first stage that ends other than `error` is what clears the record (spec: resumed branch).
- `_none_key` already holds the roadmap blob id, so clearing on an unchanged key is safe; do not change `_none_key`.
- `pick_only`, `guarded` and `_probe` are not touched.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_loop_driver.py -q`
Expected: all pass, existing tests included.

- [ ] **Step 5: Commit**

```bash
git add src/kit/loop/driver.py tests/test_loop_driver.py
git commit -m "feat(loop): record env stops until a run gets past the environment checks"
```

---

### Task 3: Show the line in `kit loop status` and `kit roadmap`; docs

**Model:** haiku

**Files:**
- Modify: `src/kit/loop_cmd.py:371-373` (`status_lines`), `src/kit/roadmap_report.py:62-71` (`format_report`), `src/kit/cli.py:14,134-135` (`roadmap_command`)
- Modify: `docs/command.md:37,40,57`, `CHANGELOG.md` (under `## Unreleased`)
- Test: `tests/test_loop_cmd_parts.py`, `tests/test_roadmap_report.py`, `tests/test_cli_pipeline.py`

**Interfaces:**
- Consumes: `alert_lines(runtime: Path) -> list[str]`, `record_env_failure` from Task 1.
- Produces: `format_report(..., alerts: list[str] | None = None) -> str` — replaces the `alert: str` parameter (the only callers are `cli.py` and tests).

- [ ] **Step 1: Write the failing tests**

`tests/test_loop_cmd_parts.py`:
```python
def test_status_lines_lead_with_the_probe_then_the_env_stop(tmp_path):
    record_probe_failure(tmp_path, datetime(2026, 11, 3, 15), "probe failed: expired")
    record_env_failure(tmp_path, datetime(2026, 11, 8, 9), "roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked")
    assert status_lines(tmp_path / "demo", tmp_path, None) == [
        "loop probe failing since 2026-11-03T15:00:00: probe failed: expired",
        "loop stopped since 2026-11-08T09:00:00: roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked",
        "no loop.log yet",
    ]
```

`tests/test_roadmap_report.py`: change `test_a_failing_probe_comes_first` to `alerts=["loop probe failing since t: why", "loop stopped since t: env"]` and assert `lines[:2]` equals that list and `lines[2].startswith("Items:")`.

`tests/test_cli_pipeline.py`: in `test_roadmap_shows_a_failing_probe_of_the_repo`, also `record_env_failure(kit_home / "loop" / repo.name, datetime(2026, 11, 8, 9), "roadmap: docs/roadmap.md:71: x")` and assert the output starts with `"loop probe failing since 2026-11-03T15:00:00: probe failed: expired\nloop stopped since 2026-11-08T09:00:00: roadmap: docs/roadmap.md:71: x\n"`. Rename it `test_roadmap_shows_the_loop_alerts_of_the_repo`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_loop_cmd_parts.py tests/test_roadmap_report.py tests/test_cli_pipeline.py -q`
Expected: the three changed tests FAIL.

- [ ] **Step 3: Implement**

- `status_lines`: `lines = alert_lines(runtime)`; import `alert_lines` instead of `probe_failure_line`.
- `format_report`: `alerts: list[str] | None = None`; `lines = [*(alerts or []), _counts(roadmap), ...]`.
- `roadmap_command`: `alerts = alert_lines(runtime_dir(args.kit_home, repo))`, pass it as the `alerts` argument; import `alert_lines`.
- `docs/command.md` line 37: append `, then a \`loop stopped since ...\` line while its last run stopped on an environment failure.` Line 40: after the probe line, add `and a \`loop stopped since ...\` line while the last run stopped on an environment failure`. After line 57, add: `- \`env-failure.txt\`: the first time and latest reason of a run that stopped on \`env\` for a reason other than the probe, kept until a run gets past the environment checks (a pick, nothing left, an unchanged roadmap and PR list, or a stage that ends other than \`error\`). The reason is kit text only: the roadmap error, a command and its exit code, or \`<stage> stage: session failed\`.`
- `CHANGELOG.md` under `## Unreleased`: `- A loop run that stops on an environment failure other than the probe is kept in \`~/.claude/kit/loop/<repo>/env-failure.txt\` with its first time and latest reason. \`kit loop status\` and \`kit roadmap\` start with \`loop stopped since <time>: <reason>\` until a run gets past the environment checks.`

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/kit/loop_cmd.py src/kit/roadmap_report.py src/kit/cli.py tests/test_loop_cmd_parts.py tests/test_roadmap_report.py tests/test_cli_pipeline.py docs/command.md CHANGELOG.md
git commit -m "feat(loop): show a loop stopped on env in loop status and roadmap"
```
