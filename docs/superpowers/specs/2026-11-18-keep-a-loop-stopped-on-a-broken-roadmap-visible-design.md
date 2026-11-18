# Keep a loop stopped on a broken roadmap visible until it runs again

Roadmap item: "Keep a loop stopped on a broken roadmap visible until it runs again" (`docs/roadmap.md`, Reliability). Small change.

## Why

From 2026-11-08 to 2026-11-18 every investment run (37 on v0.5.1) stopped with `environment failure: roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked`, because one `done` item still had a `Blocked by: nothing` line. Each run sent one `osascript` banner and wrote to `loop.log`. Nothing stayed visible, so for ten days nobody noticed. A failing probe already leaves a lasting record (`probe-failure.txt`, v0.4.3). Any other `env` stop did not.

Success: while a loop is stopped on `env` for a reason other than the probe, `kit loop status <repo>` and `kit roadmap <repo>` start with `loop stopped since <first time>: <latest reason>`, and the line goes away on its own once a run gets past the environment checks.

## How it works today

- `_Run.failed(why)` in `src/kit/loop/driver.py` counts environment failures in one run. The second one (`MAX_ERRORS = 2`) logs, sends one banner and returns `env`. It is reached from three places:
  - `_Run.pick`: `RoadmapError` from parsing `origin/<base>:docs/roadmap.md` (`roadmap: <first line>`).
  - `_Run.once` / `_run_until_stop`: a `CalledProcessError` or `OSError` from `git` or `gh` (`<cmd>: <stderr or error>`).
  - `_Run.work`: a stage that ended `error` (`<stage> stage: <detail>`). `detail` can be `session failed: <the session's result text>` (`stream.py:115`), which is session text.
- `_probe` records its own failures in `probe-failure.txt` through `src/kit/loop/alert.py` and returns `env` without calling `failed`.
- `guarded` already exits 1 on `env` (v0.4.3).
- `status_lines` (`src/kit/loop_cmd.py`) and `roadmap_command` (`src/kit/cli.py`) each read `probe_failure_line(runtime)` and put it first. `format_report` (`src/kit/roadmap_report.py`) takes it as one `alert: str`.

## Goals

- A run that stops with `env` through `_Run.failed` writes `env-failure.txt` in the runtime dir (`~/.claude/kit/loop/<repo>/`), the same shape as `probe-failure.txt`: one line, `<first time> <latest reason>`. A later `env` stop keeps the first time and replaces the reason.
- The next run that gets past the environment checks deletes the file (definition below).
- `kit loop status` and `kit roadmap` start with `loop stopped since <time>: <reason>` while the file exists.
- The recorded reason holds only text the kit wrote: the `KitError` text, a command name and exit code, or a fixed stage-error phrase. Never session text.

## Non-goals

- No change to how often the loop runs, to the banner (still one per `env` stop), to `MAX_ERRORS`, or to exit codes.
- No change to `probe-failure.txt` or the probe path.
- Crash stops (an exception reaching `guarded`) are not recorded here. They already send a banner and log the traceback.
- No new line in the cross-repo `kit status`.

## Anti-goals

- A record that outlives the problem. That would teach the owner to ignore the line.
- Session text in a file shown by `kit roadmap`. CLAUDE.md allows counts and kit text only, and the roadmap item forbids message text.
- A dry run (`kit loop run --pick-only`) that writes runtime state.

## Approaches

1. **Record in `_Run.failed` when it returns `env`; clear through one `_Run.passed()` at the points that already reset `errors = 0`. (Chosen.)** `failed` is the only place that has both the reason and the decision to stop, and the reset points are where the run has shown that git, gh and the roadmap work. It touches one class and keeps `guarded` as is.
2. Record in `guarded` when the reason is `env`. `guarded` gets only the string `env`, not the cause, so the action's return type would have to change for every caller. It would also record `--pick-only` runs. Rejected.
3. Make every `env` stop, the probe included, write one shared `loop-stopped.txt`. That changes the probe's file and its v0.4.3 line, which repos on v0.4.3+ and `docs/command.md` already describe. Rejected: it breaks shipped behaviour for no gain.

## Design

### `src/kit/loop/alert.py`

- Add `ENV_FAILURE_FILE = "env-failure.txt"` and `record_env_failure(runtime, when, why)`, `clear_env_failure(runtime)`, `env_failure_line(runtime)`. The last returns `loop stopped since <time>: <reason>`, or `""` when the file is absent.
- Share the read/record/clear code between the two files: the existing `_read` and the record body take the file name. Keep the public probe functions and their output exactly as they are.
- Add `alert_lines(runtime) -> list[str]`: the probe line, then the env line, each only when present. Both callers use it, so they cannot drift apart.

### `src/kit/loop/driver.py`

- `_Run.failed(why, shown)` takes a second argument: the reason to record. When it returns `env`, it calls `record_env_failure(env.runtime, env.now(), shown)`. Logs and the banner still use the full `why`, as today.
- The recorded `shown` text per source:
  - roadmap: `roadmap: <first line of the RoadmapError>`, the same text as `why`. For example `roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked`.
  - git/gh command error: `<cmd> failed (exit <returncode>)` for `CalledProcessError`, and `<cmd or "OSError">: <type(e).__name__>` for `OSError`. Stderr goes only to `loop.log`.
  - stage error: `<stage> stage: <detail>`, where a `session failed: ...` detail becomes just `session failed`. Kit-written details (`stage made no commit`, `pr stage reported ok but no ready PR exists`, `no result line`) are kept whole. Put the redaction in a small named function (for example `kit_reason(detail)`) with its own UNIT test.
- "Gets past the environment checks" means one of these, and each one calls `_Run.passed()`, which sets `errors = 0` and calls `clear_env_failure`:
  - `_Run.pick` parsed the roadmap and made a pick (the existing `self.errors = 0`), or found nothing left (`nothing_left`).
  - `_Run.pick` returned `done` on an unchanged `none_key`. The snapshot worked and the roadmap is the one that last parsed.
  - A stage in `_Run.work` ended with any outcome other than `error` (the existing `self.errors = 0`).
- Stops before those points do not clear the record: weekend, usage limit, a failed probe, or an `env` stop. A failed probe also does not clear it, because the probe runs before the roadmap is read.
- `pick_only` neither writes nor clears the file.
- `guarded` is not changed. The roadmap item lists it, but it never sees the cause and already exits 1 on `env`.

### `src/kit/loop_cmd.py`, `src/kit/cli.py`, `src/kit/roadmap_report.py`

- `status_lines` starts with `alert_lines(runtime)` in place of the single probe line.
- `format_report`'s `alert: str` becomes `alerts: list[str]` (default empty), printed first in order. `roadmap_command` passes `alert_lines(runtime_dir(...))`.

### Docs

- `docs/command.md`: on the `roadmap <repo>` and `loop status` lines, add the `loop stopped since ...` line. Under the runtime files, add `env-failure.txt`: the first time and latest reason of a run that stopped on `env` for a reason other than the probe, kept until a run gets past the environment checks.
- `CHANGELOG.md` under Unreleased: one entry naming the file, the line and when it clears.

### Compatibility

The file is new and only adds to the runtime dir. Older kit versions ignore it. A repo moved back to an older version keeps a stale file that it never shows, and the next run on a newer version clears or refreshes it. No migration.

### Tests

- UNIT `tests/test_loop_alert.py`: `env_failure_line` is empty with no file. Record twice: the first time is kept and the latest reason shown. A multi-line reason is collapsed to one line. Record creates a missing runtime dir. Clear is idempotent. `alert_lines` orders probe before env and leaves out absent ones. The probe tests stay unchanged.
- UNIT `tests/test_loop_driver.py` (FakeEnv), one test each:
  - A broken roadmap on two runs keeps the first run's time, with the `roadmap: ...` reason.
  - A later run that picks clears the file.
  - A later run on an unchanged `none_key` clears it.
  - A weekend run, a usage-limit probe and a failed probe each keep it.
  - Two stage errors record `<stage> stage: session failed` without the session's result text.
  - A `git`/`gh` failure records `<cmd> failed (exit N)` without stderr.
  - One failure followed by success in the same run writes nothing.
  - `pick_only` on a broken roadmap writes nothing.
- UNIT: the stage-detail redaction function on kit details and on `session failed: ...`.
- UNIT `tests/test_loop_cmd_parts.py`: `status_lines` starts with both lines when both files exist.
- UNIT `tests/test_roadmap_report.py`: `format_report` prints each alert first, in order.
- PIPELINE `tests/test_cli_pipeline.py`: extend the existing probe-failure `kit roadmap` case, or add one row, so that a recorded env failure appears as the first line. No new data-level cases.

## Left to the builder

The names of the helpers, how `alert.py` shares code between the two files, and whether `failed` takes `shown` as a parameter or works it out from a small typed reason value. Any of these is fine as long as the recorded text follows the rules above.

## Calls made for the owner

- Recorded stops: every `env` stop that goes through `_Run.failed` (roadmap, git/gh errors, two stage errors), not only roadmap errors. Rejected: recording only `RoadmapError` stops. A git, gh or stage outage would stay as invisible as the roadmap one did.
- Recorded text for non-roadmap stops is kit-written only: the command and exit code, not stderr, and `session failed` without the session's result. Rejected: storing the full `why` the way `probe-failure.txt` does. That would put session text in a file `kit roadmap` prints, against the item's "never message text".
- "Gets past the environment checks" means a successful pick, nothing left, an unchanged `none_key`, or a stage ending other than `error`, so the existing `errors = 0` points. Rejected: clearing at the start of any run that passes the probe. The roadmap is read after the probe, so the line would vanish before the broken roadmap failed again and flicker on every run.
- The record is written in `_Run.failed`, not in `guarded`. Rejected: writing it in `guarded` as the item's scope suggests. `guarded` sees only the string `env`, not the cause, and also wraps `--pick-only`.
- `kit loop run --pick-only` neither writes nor clears the record. Rejected: recording its roadmap errors too. It is a preview, and a preview should not change runtime state.
- When both records exist, the probe line comes first, then the env line. Rejected: one merged line. The two have different clear rules and the probe line's text is already documented.
- Crash stops and the cross-repo `kit status` are left out. Rejected: extending the record to crashes and adding the line to `kit status`. Both are outside the item's scope and can be their own roadmap items if wanted.
- `probe-failure.txt` and its line are not changed. Rejected: one shared `loop-stopped.txt` for both. It would change documented v0.4.3 behaviour for no gain.

## Questions for the owner
