# Name the stop reasons in the L4 finding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The L4 insights finding names failed runs per stop reason (`0 stage errors, 25 failed runs: env 25`) and points at `kit loop status <repo>` instead of permission rules.

**Architecture:** `LoopStats.failed_runs: int` becomes a derived property over a new field `failed: Mapping[str, int]` (reason -> count, `FAILED_STOPS` order, zeros left out), filled by a new `failed_by_reason` in `loopstats.py`. `findings.py` gains `failed_text` and uses it in the L4 evidence; the L4 suggestion text changes. `report.py` is untouched: its `getattr(stats, "failed_runs")` still gets an `int`.

**Tech Stack:** Python 3, dataclasses, pytest (`uv run pytest -q`).

**Spec:** `docs/superpowers/specs/2026-11-18-name-the-stop-reasons-in-the-l4-finding-design.md`

## Global Constraints

- `bench` and `insights` print counts and ratios only, never message text: the L4 evidence carries reason codes and counts only, no log or `KitError` text.
- No change to `src/kit/loop/driver.py`, the ledger format, `src/kit/insights/report.py`, the L4 firing rule (`errors or failed_runs`) or any other finding.
- `docs/code-conventions.md`: typed named results, minimal functions, UNIT tests beside each module; no PIPELINE test.
- Tests run offline with fixtures built in code; never read the real `~/.claude/projects/`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- `tests/test_insights_report.py` builds `LoopStats` positionally with `0` in the 8th slot (the old `failed_runs`). After the change that slot is `failed`; a leftover `0` makes `failed_runs` raise `AttributeError: 'int' object has no attribute 'values'` when the report table is built. The spec's scope list misses this file; Task 1 changes both constants to `{}` and the report tests pin it.
- A week with only stage errors (`failed == {}`) must not end the evidence with `": "`. Task 2 tests `2 stage errors, 0 failed runs` exactly.
- Stop reasons outside `FAILED_STOPS` (`limit`, `usage`, `done`, or an unknown future code) must not appear in `failed` nor in the L4 text. Task 1 tests it with a `done`, `limit` and unknown `"weird"` stop.
- The order of reasons in the evidence must be fixed (`env` before `crash`) regardless of ledger order. Task 1 feeds `crash` before `env`.
- `LoopStats` must stay hashable/frozen-compatible as before: a `dict` field in a frozen dataclass is fine for equality but makes instances unhashable; nothing hashes `LoopStats` today (`usd` is already a dict), so no change needed — reviewer confirms no `set`/dict-key use of `LoopStats` was added.

---

### Task 1: Per-reason failed-run counts in `LoopStats`

**Model:** haiku

**Files:**
- Modify: `src/kit/insights/loopstats.py:18-29` (`LoopStats`), `:75-90` (`loop_stats`), new function after `stop_entries`
- Modify: `tests/test_insights_loopstats.py`
- Modify: `tests/test_insights_report.py:10-11` (positional `LoopStats` constants)
- Modify: `tests/test_insights_findings.py:12,34` (the `stats()` helper and the L4 case), so the suite stays green

**Interfaces:**
- Produces: `failed_by_reason(stops: list[StopEntry]) -> dict[str, int]`; `LoopStats.failed: Mapping[str, int]` (same position as the old `failed_runs`, between `usage_stops` and `usd`); property `LoopStats.failed_runs -> int` = `sum(self.failed.values())`.

- [ ] **Step 1: Write the failing tests** in `tests/test_insights_loopstats.py` (import `failed_by_reason`):

```python
def test_failed_by_reason_counts_failed_stops_in_failed_stops_order():
    stops = [StopEntry(T, "v0.3.0", r) for r in ("crash", "env", "limit", "env", "done", "weird")]
    assert list(failed_by_reason(stops).items()) == [("env", 2), ("crash", 1)]
    assert failed_by_reason([StopEntry(T, "v0.3.0", "env")]) == {"env": 1}
    assert failed_by_reason([StopEntry(T, "v0.3.0", "done")]) == {}
```

and in `test_loop_stats_counts_and_dollars` add `assert s.failed == {"crash": 1}` (the existing tuple assertion keeps `s.failed_runs == 1`). Add `assert s.failed == {} and s.failed_runs == 0` to `test_loop_stats_with_nothing_is_nan_not_an_error`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest -q tests/test_insights_loopstats.py`
Expected: FAIL with `ImportError: cannot import name 'failed_by_reason'`

- [ ] **Step 3: Implement** in `src/kit/insights/loopstats.py`: `failed_by_reason` (iterate `FAILED_STOPS`, count matching `e.reason`, keep counts > 0); replace field `failed_runs: int` with `failed: Mapping[str, int]  # failed runs per stop reason, FAILED_STOPS order`; add property `failed_runs`; `loop_stats` passes `failed=failed_by_reason(stops)`.

- [ ] **Step 4: Fix the other `LoopStats` builders**

- `tests/test_insights_report.py`: in `EMPTY` and `BUSY`, the 8th positional argument `0` becomes `{}`.
- `tests/test_insights_findings.py`: in `stats()`, `failed_runs=0` becomes `failed={}`; in `test_each_loop_rule_fires_on_its_own`, `stats(failed_runs=1)` becomes `stats(failed={"env": 1})`.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/kit/insights/loopstats.py tests/test_insights_loopstats.py tests/test_insights_report.py tests/test_insights_findings.py
git commit -m "feat(insights): keep failed loop runs per stop reason"
```

### Task 2: L4 names the stop reasons and points at `kit loop status <repo>`

**Model:** haiku

**Files:**
- Modify: `src/kit/insights/findings.py:5` (import `Mapping`), new function before `loop_findings`, `:59-60` (L4)
- Modify: `tests/test_insights_findings.py`
- Modify: `CHANGELOG.md` (under `## Unreleased`)

**Interfaces:**
- Consumes: `LoopStats.failed: Mapping[str, int]` and `LoopStats.failed_runs -> int` from Task 1.
- Produces: `failed_text(failed: Mapping[str, int]) -> str` in `kit.insights.findings`.

- [ ] **Step 1: Write the failing tests** in `tests/test_insights_findings.py` (import `failed_text`):

```python
SUGGESTION = "read the last lines of `kit loop status <repo>`; `env` means the probe, the roadmap or a `read_first` path failed before any stage, or a `git`/`gh` command kept failing"


def test_failed_text_joins_reason_and_count():
    assert failed_text({"env": 2, "crash": 1}) == "env 2, crash 1"
    assert failed_text({}) == ""


def test_l4_names_the_stop_reasons():
    [f] = findings([week(stats(failed={"env": 25}))])
    assert (f.key, f.evidence, f.suggestion) == ("L4", "0 stage errors, 25 failed runs: env 25", SUGGESTION)
    [f] = findings([week(stats(errors=1, failed={"env": 2, "crash": 1}))])
    assert f.evidence == "1 stage errors, 3 failed runs: env 2, crash 1"


def test_l4_with_stage_errors_only_has_no_reason_suffix():
    [f] = findings([week(stats(errors=2))])
    assert f.evidence == "2 stage errors, 0 failed runs"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest -q tests/test_insights_findings.py`
Expected: FAIL with `ImportError: cannot import name 'failed_text'`

- [ ] **Step 3: Implement** in `src/kit/insights/findings.py`: `failed_text` returns `", ".join(f"{reason} {count}" for ...)`. L4 evidence is `f"{s.errors} stage errors, {s.failed_runs} failed runs"` plus `f": {failed_text(s.failed)}"` only when `s.failed_runs`. L4 suggestion is exactly the `SUGGESTION` string above (no trailing `.`; `finding_lines` adds it). The permission-denials hint is removed.

- [ ] **Step 4: Add the CHANGELOG line** under `## Unreleased` in `CHANGELOG.md`, above the existing bullet, in the existing style:

```markdown
- The L4 insights finding names failed loop runs per stop reason (`0 stage errors, 25 failed runs: env 25`) and suggests reading the last lines of `kit loop status <repo>`, saying what `env` means, instead of pointing at permission rules. The 2026-W46 report sent the advisor to a missing allow rule when every run had stopped with `env` on a roadmap error. The ledger is unchanged; re-running `kit insights` for older weeks changes only the L4 text.
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/kit/insights/findings.py tests/test_insights_findings.py CHANGELOG.md
git commit -m "feat(insights): name the stop reasons in the L4 finding"
```
