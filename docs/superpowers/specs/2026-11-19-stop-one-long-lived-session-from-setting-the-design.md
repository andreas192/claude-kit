# Stop one long-lived session from setting the session duration median — design

Roadmap item: `docs/roadmap.md`, "Insights accuracy" › "Stop one long-lived session from setting the session duration median".

## Intent

S1 (`session duration, median (min)`) was 11,623 minutes in dividend-growth and 11,658 in investment for 2026-W46. In each case one session ran about eight days from its first message to its last, most likely because it was resumed. Today `minutes(session)` in `src/kit/bench/measures.py` is `main.end - main.start` in wall-clock time, so a session that is resumed days later counts every idle hour in between. One such session makes a whole week's S1 meaningless, both in `kit bench` and in `kit insights` (which shows S1 as a session row, `src/kit/insights/report.py` `SESSION_KEYS`).

S1 should measure how long someone actually worked in a session: active time, not wall-clock span.

## Goals

- S1 counts active time. Active time is the sum of the gaps between consecutive timestamped records, leaving out every gap longer than `IDLE_GAP_MINUTES = 30`.
- One resumed session can no longer move a week's S1 by days.
- `CHANGELOG.md` says what S1 now means, because bench and insights tables for older weeks change when they are re-run.

## Non-goals

- Which week or version window a session belongs to. That stays decided by `main.start` (`src/kit/bench/windows.py`). A session resumed into a later week still counts in its start week.
- Any other measure (F1–F3, Q1–Q3, S2, B1–B13) and the insights finding thresholds. The insights finding keys `S1`–`S6` in `src/kit/insights/findings.py` are a separate namespace from the bench measure `S1` and are not touched.
- Earlier bench results already written under `.claude/kit-bench/`. They are not rewritten; a re-run gives the new numbers.
- A flag to choose between wall-clock and active time. One obvious meaning.

## Anti-goals

- Reading or keeping message text. Only the `timestamp` field of each record is used.
- A new data source. Timestamps are already in every transcript on disk.

## Constraints (from CLAUDE.md and `docs/code-conventions.md`)

- `bench` writes only `.claude/kit-bench/`; `insights` writes only `~/.claude/kit/insights/`. Neither changes.
- Counts and ratios only in output.
- Minimal, type-hinted functions; named constant; UNIT tests beside each module (`tests/test_measures.py`, `tests/test_transcripts.py`); no new PIPELINE test. `bench/run.py` stays wiring.
- Tests build transcripts in code and never read `~/.claude/projects/`.

## Approaches

1. **Keep every timestamp, compute active time in `measures.py` (chosen).** `parse_transcript` appends each record's `timestamp` to a new `Transcript.times: list[str]` field (default empty). `measures.active_minutes(session)` parses the times of the main transcript and its subagents, sorts them, and sums the gaps of at most `IDLE_GAP_MINUTES`. The rule lives in one small, testable function next to `m_duration`, and the parser stays a plain recorder.
2. **Accumulate active seconds while parsing.** `parse_transcript` adds each gap to `Transcript.active_seconds` as it reads. Cheaper in memory, but it puts the idle rule inside the parser, works on one transcript at a time and so cannot merge the main session with its subagents, and makes the rule harder to test on its own.
3. **Cap or trim the median instead** (drop sessions over N hours, or use a trimmed mean). Hides the outlier without measuring the right thing: a resumed session that had two hours of real work would vanish entirely. Rejected.

## Design

- `src/kit/bench/transcripts.py`: `Transcript` gains `times: list[str] = field(default_factory=list)`. In `parse_transcript`, every record with a non-empty `timestamp` appends it. `start` and `end` stay as they are, because windows and `since` filtering use `start`.
- `src/kit/bench/measures.py`:
  - `IDLE_GAP_MINUTES = 30`, a module constant.
  - `active_minutes(times: list[datetime], idle_gap_minutes: float = IDLE_GAP_MINUTES) -> float`: sorts the times and sums each consecutive gap that is at most the idle gap, in minutes. A gap of exactly 30 minutes counts; a longer gap counts as zero (not as 30). One time gives `0.0`.
  - `session_times(session: Session) -> list[datetime]`: the parseable times of `transcripts(session)` (main and every subagent); unparseable or empty strings are skipped.
  - `minutes(session) -> float | None`: `None` when `session_times` is empty, otherwise `active_minutes(...)`.
  - `m_duration` is unchanged apart from now calling the new `minutes`.
  - The S1 label becomes `session active time, median (min)`. Key `S1` and direction `falls` stay.
- `CHANGELOG.md`, under `## Unreleased`: S1 is now active time (sum of gaps between consecutive messages of the session and its subagents, leaving out gaps over 30 minutes), not first-to-last message; re-running `kit bench` or `kit insights` for older weeks gives different S1 values; earlier results under `.claude/kit-bench/` are not rewritten.

### Tests (all UNIT)

`tests/test_measures.py`:
- `active_minutes` sums gaps of at most 30 minutes and leaves out a longer one (for example 07:00, 07:10, 07:40, then 3 days later 09:00, 09:05 → 45).
- A gap of exactly 30 minutes counts; 31 minutes does not.
- Unsorted input gives the same result as sorted.
- One time → `0.0`.
- `minutes` merges main and subagent times: a main transcript waiting 45 minutes on a subagent that writes every few minutes counts the subagent's activity.
- `minutes` skips unparseable times and returns `None` when none parse; S1 is NaN for such sessions (existing `test_duration_skips_sessions_without_timestamps` keeps passing).
- Existing tests that set only `start`/`end` (`test_duration_is_median_minutes`, the aware/naive and one-unparseable-time tests) are rewritten to set `times`, since `start`/`end` no longer drive S1. The aware/naive case keeps proving that mixing `Z` and zone-less times does not crash.
- The S1 label test, if any asserts the old label, is updated.

`tests/test_transcripts.py`:
- `parse_transcript` records every non-empty `timestamp` in order in `times`, and skips records without one.

`tests/builders.py`: `session(...)` gains an optional `times` argument passed to the main `Transcript`.

## Calls made for the owner

- Active time is computed over the merged timestamps of the main transcript and all its subagents, not the main transcript alone. A main session waiting 45 minutes on an implementer is working, not idle. Rejected: main transcript only, as the roadmap's "consecutive messages" could be read, which would drop every long subagent run as idle time.
- A gap longer than `IDLE_GAP_MINUTES` contributes nothing, not a capped 30 minutes. That matches the roadmap's "leaving out any gap". Rejected: capping each long gap at 30 minutes, which still adds time nobody worked.
- A gap of exactly 30 minutes counts as active ("over" 30 is left out). Rejected: excluding gaps of 30 minutes or more.
- Every record with a `timestamp` counts as activity (user, assistant, tool result, attachment), not only user and assistant messages. Rejected: filtering record types, which adds rules without changing the result in practice, because tool results and attachments sit between messages.
- A session with one parseable timestamp has S1 `0.0`; one with none is skipped (NaN when no session has any). Rejected: skipping single-record sessions, which would treat a real but short session as missing.
- Keep the timestamps on `Transcript.times` and compute in `measures.py` (Approach 1). Rejected: accumulating active seconds in the parser (Approach 2), which cannot merge subagents and hides the rule in the parser.
- The S1 label changes to `session active time, median (min)` so the table says what it measures; key `S1` stays so insights rows and older reports still line up. Rejected: keeping the old label, which would hide the changed meaning from anyone reading a table.
- Week and version-window assignment stay on `main.start`. Rejected: splitting a resumed session across weeks, which is a larger change to `windows.py` outside this item's scope.
- No version bump in this change; the CHANGELOG entry goes under `## Unreleased` and the release skill cuts the version. Rejected: bumping the version here.

## Questions for the owner

## Left to the builder

- Exact names of the helper functions and whether `session_times` returns a list or a tuple.
- How the test fixtures express times (ISO strings with `Z` throughout, plus one zone-less case).
