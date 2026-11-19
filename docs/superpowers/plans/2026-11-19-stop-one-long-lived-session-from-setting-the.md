# Stop one long-lived session from setting the session duration median Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** S1 measures a session's active time (sum of gaps of at most 30 minutes between consecutive timestamps of the main transcript and its subagents) instead of first-to-last wall-clock span.

**Architecture:** `parse_transcript` records every non-empty `timestamp` on a new `Transcript.times` list. `measures.py` merges the times of the main transcript and its subagents, parses them with the existing `parse_utc`, sorts them and sums the gaps up to `IDLE_GAP_MINUTES`. `m_duration` and week/window assignment (`main.start`) are otherwise unchanged.

**Tech Stack:** Python 3 standard library, pytest, `uv run pytest -q`.

**Spec:** `docs/superpowers/specs/2026-11-19-stop-one-long-lived-session-from-setting-the-design.md`

## Global Constraints

- `IDLE_GAP_MINUTES = 30`, a module constant in `src/kit/bench/measures.py`.
- A gap of exactly 30 minutes counts; a gap over 30 minutes contributes `0`, not 30.
- One parseable time → `0.0`; no parseable time → `minutes` returns `None` (session skipped; S1 NaN when no session has a time).
- S1 label: `session active time, median (min)`. Key `S1` and direction `falls` stay.
- Only each record's `timestamp` field is read; no message text is kept. Output stays counts and ratios.
- `Transcript.start` / `end` stay as they are; windows and `since` filtering keep using `main.start`.
- No flag to choose wall-clock vs active time. No version bump; CHANGELOG entry goes under `## Unreleased`.
- UNIT tests only (`tests/test_transcripts.py`, `tests/test_measures.py`); tests build transcripts in code and never read `~/.claude/projects/`. No new PIPELINE test.
- Follow `docs/code-conventions.md`: minimal, type-hinted functions.

## Review Focus

- A session whose main transcript has no parseable times but whose subagent has some still gets an S1 value from the subagent times (spec: `None` only when `session_times` is empty). Test added in Task 2.
- Streamed records of one message share a timestamp, so duplicate times appear; a zero gap must add `0` and not break the sum. Test added in Task 2.
- Mixing `Z` and zone-less times must not raise when sorting (`parse_utc` makes both aware). Covered by the rewritten aware/naive test in Task 2.
- Sessions built without `times` (every other existing test using `builders.session(...)`, insights report tests) now give NaN for S1 instead of a span; no other test may depend on S1 from `start`/`end`. Task 2 Step 4 runs the full suite to prove it.
- A record whose `timestamp` is not a string or is empty is not appended. Test added in Task 1.

---

### Task 1: Record every timestamp on `Transcript.times`

Model: haiku

**Files:**
- Modify: `src/kit/bench/transcripts.py` (`Transcript` dataclass, `parse_transcript`)
- Test: `tests/test_transcripts.py`

**Interfaces:**
- Produces: `Transcript.times: list[str] = field(default_factory=list)` — every non-empty `timestamp` string, in file order.

- [ ] **Step 1: Write the failing test** in `tests/test_transcripts.py` (uses existing builders `rec`, `user`, `assistant`):

```python
def test_parse_records_every_timestamp_in_order_and_skips_records_without_one() -> None:
    t = parse_transcript([rec("2026-10-17T07:00:00Z"), user("hi"), assistant("a"), rec(""), rec("2026-10-17T06:00:00Z")])
    assert t.times == ["2026-10-17T07:00:00Z", "2026-10-17T07:00:00Z", "2026-10-17T06:00:00Z"]
```

(`user("hi")` has no timestamp; `rec("")` is an empty one; `assistant("a")` carries `2026-10-17T07:00:00Z`; the out-of-order last time shows `times` keeps file order and does not sort.)

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_transcripts.py -q`
Expected: FAIL with `AttributeError: 'Transcript' object has no attribute 'times'`

- [ ] **Step 3: Implement.** Add `times: list[str] = field(default_factory=list)` to `Transcript` (after `end`). In `parse_transcript`, after reading `timestamp`, append it to `transcript.times` when it is a non-empty `str`. Leave `start`/`end` logic unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_transcripts.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/kit/bench/transcripts.py tests/test_transcripts.py
git commit -m "feat(bench): record every transcript timestamp"
```

---

### Task 2: S1 counts active time

Model: sonnet

**Files:**
- Modify: `src/kit/bench/measures.py` (constant, `active_minutes`, `session_times`, `minutes`, S1 label)
- Modify: `tests/builders.py` (`session(...)` gains `times`)
- Modify: `tests/test_measures.py` (new tests; rewrite the four S1 tests that set `start`/`end`)
- Modify: `CHANGELOG.md` (`## Unreleased`)

**Interfaces:**
- Consumes: `Transcript.times: list[str]` (Task 1); `kit.bench.windows.parse_utc(text: str) -> datetime | None` (existing).
- Produces:
  - `IDLE_GAP_MINUTES = 30`
  - `active_minutes(times: list[datetime], idle_gap_minutes: float = IDLE_GAP_MINUTES) -> float`
  - `session_times(session: Session) -> list[datetime]` — parseable times of `transcripts(session)` (main and every subagent), unparseable/empty skipped.
  - `minutes(session: Session) -> float | None` — `None` when `session_times` is empty, else `active_minutes(session_times(session))`.
  - `builders.session(..., times: list[str] = ())` — passed as `times=list(times)` to the main `Transcript`.

- [ ] **Step 1: Write the failing tests.** In `tests/builders.py`, add the `times` parameter to `session(...)` first (it is test scaffolding). In `tests/test_measures.py`, import `datetime`, `timezone`, and `IDLE_GAP_MINUTES, active_minutes` from `kit.bench.measures`, and add a helper `at(text: str) -> datetime` that returns `datetime.fromisoformat(text.replace("Z", "+00:00"))`. Then:

```python
def test_active_minutes_leaves_out_a_gap_over_the_idle_gap() -> None:
    times = ["2026-10-17T07:00:00Z", "2026-10-17T07:10:00Z", "2026-10-17T07:40:00Z", "2026-10-20T09:00:00Z", "2026-10-20T09:05:00Z"]
    assert active_minutes([at(t) for t in times]) == 45.0

def test_a_gap_of_exactly_the_idle_gap_counts_and_one_minute_more_does_not() -> None:
    assert IDLE_GAP_MINUTES == 30
    assert active_minutes([at("2026-10-17T07:00:00Z"), at("2026-10-17T07:30:00Z")]) == 30.0
    assert active_minutes([at("2026-10-17T07:00:00Z"), at("2026-10-17T07:31:00Z")]) == 0.0

def test_active_minutes_sorts_its_input() -> None:
    times = [at("2026-10-17T07:40:00Z"), at("2026-10-17T07:00:00Z"), at("2026-10-17T07:10:00Z")]
    assert active_minutes(times) == 40.0

def test_one_time_is_zero_minutes() -> None:
    assert active_minutes([at("2026-10-17T07:00:00Z")]) == 0.0

def test_duplicate_times_add_nothing() -> None:
    assert active_minutes([at("2026-10-17T07:00:00Z")] * 3 + [at("2026-10-17T07:05:00Z")]) == 5.0

def test_duration_merges_main_and_subagent_times() -> None:
    sub = Subagent("kit:implementer-sonnet", "Task 1", Transcript(times=["2026-10-17T07:05:00Z", "2026-10-17T07:15:00Z", "2026-10-17T07:25:00Z", "2026-10-17T07:35:00Z"]))
    s = session(times=["2026-10-17T07:00:00Z", "2026-10-17T07:45:00Z"], subagents=[sub])
    assert measure("S1", [s]) == 45.0

def test_duration_uses_subagent_times_when_main_has_none() -> None:
    sub = Subagent("x", "", Transcript(times=["2026-10-17T07:00:00Z", "2026-10-17T07:20:00Z"]))
    assert measure("S1", [session(subagents=[sub])]) == 20.0

def test_duration_label_says_active_time() -> None:
    assert next(m for m in MEASURES if m.key == "S1").label == "session active time, median (min)"
```

Rewrite the existing S1 tests to set `times` instead of `start`/`end`:

```python
def test_duration_is_median_minutes() -> None:
    short = session(times=["2026-10-17T07:00:00Z", "2026-10-17T07:10:00Z"])
    mid = session(times=["2026-10-17T07:00:00Z", "2026-10-17T07:20:00Z", "2026-10-17T07:30:00Z"])
    resumed = session(times=["2026-10-17T07:00:00Z", "2026-10-17T07:25:00Z", "2026-10-25T07:00:00Z", "2026-10-25T07:20:00Z"])
    assert measure("S1", [short, mid, resumed]) == 30.0

def test_duration_skips_sessions_without_timestamps() -> None:
    assert math.isnan(measure("S1", [session()]))

def test_duration_mixing_aware_and_naive_times_does_not_crash() -> None:
    assert measure("S1", [session(times=["2026-10-17T07:00:00Z", "2026-10-17T07:30:00"])]) == 30.0

def test_duration_skips_unparseable_times() -> None:
    assert measure("S1", [session(times=["2026-10-17T07:00:00Z", "garbage", "2026-10-17T07:10:00Z"])]) == 10.0
    assert math.isnan(measure("S1", [session(times=["garbage", ""])]))
```

(`resumed` is 25 + 20 = 45 active minutes; the median of 10, 30, 45 is 30. The last test replaces `test_duration_skips_a_session_with_one_unparseable_time`.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_measures.py -q`
Expected: FAIL with `ImportError: cannot import name 'IDLE_GAP_MINUTES'`

- [ ] **Step 3: Implement in `src/kit/bench/measures.py`.** Add `IDLE_GAP_MINUTES = 30`, `active_minutes`, `session_times`, and replace `minutes` with the signatures from Interfaces. `active_minutes` sorts, takes consecutive differences in minutes, and sums those `<= idle_gap_minutes`. `session_times` uses `parse_utc` on every string in `t.times` for `t in transcripts(session)`, keeping non-`None` results. Change the S1 label to `session active time, median (min)`. `m_duration` stays as is.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass (no other test depends on S1 from `start`/`end`; `tests/test_windows.py` still passes `start`/`end` and is unaffected).

- [ ] **Step 5: Add the CHANGELOG entry** as the first bullet under `## Unreleased` in `CHANGELOG.md`:

```markdown
- S1 in `kit bench` and `kit insights` is now `session active time, median (min)`: the sum of the gaps between consecutive timestamped records of the session and its subagents, leaving out every gap over 30 minutes. It used to be the time from the first to the last message, so one session resumed days later (about eight days in dividend-growth and investment for 2026-W46) set a whole week's median. Re-running `kit bench` or `kit insights` for older weeks gives different S1 values; results already under `.claude/kit-bench/` are not rewritten. A session still counts in the week and version window of its first record.
```

- [ ] **Step 6: Commit**

```bash
git add src/kit/bench/measures.py tests/builders.py tests/test_measures.py CHANGELOG.md
git commit -m "feat(bench): S1 counts active time, not first-to-last span"
```
