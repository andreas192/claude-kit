# Name the stop reasons in the L4 finding — design

Roadmap item: "Name the stop reasons in the L4 finding" (`docs/roadmap.md`, Reliability). Size: a small change.

## Why

The 2026-W46 insights report said only "0 stage errors, 25 failed runs" for investment, and the L4 suggestion pointed at permission denials. The insights advisor, which sees only the report, guessed a missing `Bash(uv run pytest*)` allow rule. The real cause was a roadmap validation error: every run stopped with `env` before any stage. `stages.jsonl` already records each run's stop `reason`, so the report can say which kind of failure it was without reading any log text.

## How it works today

- `src/kit/loop/driver.py` writes one `StopEntry(time, kit_version, reason)` per run. `reason` is a short code: `env` (the probe, the roadmap or a `read_first` path failed before any stage, or a `git`/`gh`/stage command raised `MAX_ERRORS` times in one run, see `_Run.failed`), `crash` (the run raised), and non-failure codes such as `limit`, `usage`, `done`.
- `src/kit/insights/loopstats.py`: `FAILED_STOPS = ("env", "crash")`; `loop_stats` sets `LoopStats.failed_runs` to the number of stops whose reason is in `FAILED_STOPS`. The per-reason split is thrown away.
- `src/kit/insights/findings.py`: L4 fires when `errors or failed_runs`, with evidence `f"{errors} stage errors, {failed_runs} failed runs"` and suggestion "read `kit loop status`; permission denials go in `.claude/loop-settings.json`".
- `src/kit/insights/report.py` reads `failed_runs` by `getattr` for the "failed runs" table row. Nothing else builds `LoopStats` except `loop_stats` and the test helper in `tests/test_insights_findings.py`.

## Goals

- `LoopStats` keeps the failed-run count per stop reason.
- L4 evidence names the reasons with their counts, for example `0 stage errors, 25 failed runs: env 25`.
- L4 suggestion points at the last lines of `kit loop status <repo>` and says what `env` means (exact text under Design).

## Non-goals

- No new sub-reasons in the ledger (probe vs roadmap vs `read_first`). The driver and `stages.jsonl` stay as they are; the item says the ledger already holds what is needed.
- No change to `report.py` tables, to the L4 firing rule, or to any other finding.
- No change to `kit loop status` or the alert files (that is the separate item "Keep a loop stopped on a broken roadmap visible until it runs again").

## Anti-goals

- Any log text, `KitError` text or message text in the report. Counts and reason codes only (CLAUDE.md: `insights` prints counts and ratios only; the advisor sees only that report).

## Constraints

- Scope: `src/kit/insights/loopstats.py`, `src/kit/insights/findings.py`, `tests/test_insights_loopstats.py`, `tests/test_insights_findings.py`, plus a `CHANGELOG.md` line.
- `docs/code-conventions.md`: typed named results, minimal functions, UNIT tests beside each module; no PIPELINE test needed (the wiring is unchanged).
- `insights` writes only `~/.claude/kit/insights/`; unchanged.

## Approaches

1. **Replace the int with a per-reason mapping (picked).** `LoopStats` gets `failed: Mapping[str, int]` (reason -> count, `FAILED_STOPS` order, zero counts left out), and `failed_runs` becomes a property summing it. One source of truth; `report.py`'s `getattr(stats, "failed_runs")` keeps working unchanged because the property returns an `int`.
2. Add `failed_by_reason` next to the existing `failed_runs: int`. Smaller diff, but two fields that can disagree, and every builder of `LoopStats` must keep them in step.
3. Have `findings.py` count reasons from the raw ledger entries. `Week` holds `LoopStats`, not entries, so this would widen `Week` and move counting out of `loopstats.py`, which owns it.

## Design

`loopstats.py`:

- New function `failed_by_reason(stops: list[StopEntry]) -> dict[str, int]`: for each reason in `FAILED_STOPS`, in that order, the count of stops with that reason; reasons with a count of 0 are left out. Other reasons are ignored.
- `LoopStats`: field `failed_runs: int` is replaced by `failed: Mapping[str, int]  # failed runs per stop reason, FAILED_STOPS order`; new property `failed_runs -> int` returns `sum(self.failed.values())`.
- `loop_stats` sets `failed=failed_by_reason(stops)`.

`findings.py`:

- New function `failed_text(failed: Mapping[str, int]) -> str`: `"env 25, crash 1"` (reason, space, count, joined by `", "`), empty string for an empty mapping.
- L4 evidence: `f"{s.errors} stage errors, {s.failed_runs} failed runs"`, followed by `f": {failed_text(s.failed)}"` when there is at least one failed run. Examples: `0 stage errors, 25 failed runs: env 25`; `2 stage errors, 0 failed runs`; `1 stage errors, 3 failed runs: env 2, crash 1`.
- L4 suggestion, the roadmap item's text plus the repeated-command case: "read the last lines of `kit loop status <repo>`; `env` means the probe, the roadmap or a `read_first` path failed before any stage, or a `git`/`gh` command kept failing". `finding_lines` adds the trailing `.`.

Tests (all UNIT):

| Test | Proves |
| --- | --- |
| `test_insights_loopstats.py`: `failed_by_reason` over env, crash, limit, done stops | per-reason counts, `FAILED_STOPS` order, zero and non-failure reasons left out |
| `test_insights_loopstats.py`: existing `test_loop_stats_counts_and_dollars` | `failed_runs` property still 1 and `failed == {"crash": 1}` |
| `test_insights_findings.py`: `failed_text` | format and empty mapping |
| `test_insights_findings.py`: L4 evidence with `failed={"env": 25}` | `0 stage errors, 25 failed runs: env 25`; suggestion names `kit loop status <repo>` and `env` |
| `test_insights_findings.py`: L4 with stage errors only | no `:` suffix |

The `stats()` helper in `test_insights_findings.py` changes `failed_runs=0` to `failed={}`, and the existing L4 case becomes `stats(failed={"env": 1})`.

`CHANGELOG.md`, under `## Unreleased`: one line saying the L4 finding now names failed runs per stop reason and points at `kit loop status <repo>`, and that re-running `kit insights` for older weeks changes only the L4 text.

## Backwards compatibility and measurement

- The ledger format is unchanged, so reports for older weeks re-run with the same numbers; only the L4 wording changes. `LoopStats` is internal to insights; no repo on an older kit version reads it.
- Measured by the next insights report: an `env`-only week shows `failed runs: env N` and the advisor's suggestion should name the probe, roadmap or `read_first`, not permissions.

## Left to the builder

- Exact test names and fixture shapes.
- Whether `failed_text` lives in `findings.py` or as a small helper beside `fmt`; `findings.py` is the default.

## Calls made for the owner

- Kept the `N stage errors, ` prefix in the L4 evidence even when it is 0, and appended `: env 25` after the failed-run count. Rejected: dropping zero parts so it reads only `25 failed runs: env 25` (the roadmap's example), because one fixed shape is easier to read across weeks and the stage-error count is half of what L4 fires on.
- Replaced `failed_runs: int` with a `failed` per-reason mapping and made `failed_runs` a derived property. Rejected: a second `failed_by_reason` field beside the int, which can drift from it.
- Left out reasons with a zero count, in `FAILED_STOPS` order (`env`, then `crash`). Rejected: always printing both (`env 25, crash 0`), which adds noise; and sorting by count, which changes order week to week.
- Added ", or a `git`/`gh` command kept failing" to the roadmap's suggestion text, because `_Run.failed` in `driver.py` also stops a run with `env` after `MAX_ERRORS` command failures. Rejected: the roadmap text verbatim, which would send the advisor to the probe or roadmap for a stop that came from neither.
- Dropped the permission-denials hint from the suggestion, as the roadmap text does. Rejected: keeping "permission denials go in `.claude/loop-settings.json`" when stage errors > 0, since that hint is what misled the W46 advisor and per-session permission denials already have their own finding (S5).
- Wrote `<repo>` literally in the suggestion. Rejected: filling in the repo name, which `loop_findings` does not receive and the report's `## <repo>` heading already shows.
- Kept the bare `kit loop status` form from the roadmap text in the report. Rejected: the full `uv run --project ... kit` command, since the report is read, not run, and the kit-command guard already corrects a bare call in a session.
- No new loop table rows per reason in `report.py`. Rejected: `failed runs: env` / `failed runs: crash` rows, because `report.py` is outside the item's scope and the finding already carries the split.
- Added a `CHANGELOG.md` line under `## Unreleased`. Rejected: no entry, because the report wording the owner and advisor read changes.

## Questions for the owner

