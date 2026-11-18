# Roadmap

What this repo will build next, in priority order. `uv run --project ~/Projects/Personal/claude-kit kit roadmap <repo>` validates this file and shows what the loop would pick next.

## How to add an item

Put each item under a `## ` section of any name, as a `### ` heading with a unique title. Right after the heading come field lines (`- Name: value`); free Markdown after them describes the item. The order in the file is the priority order.

Status is required and means:

- `open`: needs no decision from the owner. The loop takes only these, the first one in file order whose `Depends on` items are all `done`.
- `owner`: needs the owner (a decision, an input, or the owner's own hands). These are the weekend list. Add `Blocked by` with what it waits for.
- `blocked`: waits on something other than the owner, such as upstream data or another item. Add `Blocked by`.
- `active`: someone is working on it outside the loop.
- `done`: landed.
- `dropped`: will not be built.

Other fields: `Depends on` (comma-separated titles from this file), and `Spec`, `Plan`, `PR` (a path or URL), and `Requested by` (the sibling repo directory that asked for this item through `uv run --project ~/Projects/Personal/claude-kit kit request`; set by the kit). The PR that lands an item sets its Status to `done` and fills in Spec, Plan and PR. When unsure whether an item is `open`, mark it `owner`.

## Reliability

### Make a failed loop probe hard to miss
- Status: done
- PR: https://github.com/andreas192/claude-kit/pull/17

A failed probe stopped both loops for two days while launchd reported exit code 0 and `launchd.log` stayed empty. See `docs/reports/2026-11-05-loop-auth-outage.md`.

Scope: `src/kit/loop/driver.py` (`guarded`) and `src/kit/loop_cmd.py`. Exit non-zero when a run stops with `env`, and record the stop so `kit loop status` and `kit roadmap` show it until a later probe succeeds. Check that `osascript` banners are delivered from launchd, and keep the existing `notify` path if they are. A probe failure must still cost nothing and must not retry in a loop.

### Keep a loop stopped on a broken roadmap visible until it runs again
- Status: open

From 2026-11-08 to 2026-11-18 every investment run (37 on v0.5.1) stopped with `environment failure: roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked`: one `done` item kept a `Blocked by: nothing` line. Each run sent one `osascript` banner and nothing else, so nobody noticed for ten days. A failing probe already leaves a lasting line; this stop did not.

Scope: `src/kit/loop/alert.py`, `src/kit/loop/driver.py` (`guarded`), `src/kit/loop_cmd.py` (`status_lines`) and `src/kit/roadmap_report.py`. When a run stops with `env` for a reason other than the probe, keep the first time and the latest reason in one file in the runtime dir (`env-failure.txt`, same shape as `probe-failure.txt`), and clear it on the next run that gets past the environment checks. `kit loop status` and `kit roadmap` start with `loop stopped since <time>: <reason>` while it lasts. The reason is the `KitError` text only, never message text. UNIT tests in `tests/test_loop_alert.py` and the driver tests; no change to how often the loop runs.

### Name the stop reasons in the L4 finding
- Status: open

The 2026-W46 insights report said only "0 stage errors, 25 failed runs" for investment and pointed at permission denials. The advisor then guessed a missing `Bash(uv run pytest*)` allow rule, but the real cause was a roadmap validation error. `stages.jsonl` already records each stop's `reason`.

Scope: `src/kit/insights/loopstats.py`, `src/kit/insights/findings.py` and their tests. Count failed runs per stop reason (`env`, `crash`) and put the counts in the L4 evidence (for example `25 failed runs: env 25`). Change the L4 suggestion to "read the last lines of `kit loop status <repo>`; `env` means the probe, the roadmap or a `read_first` path failed before any stage". Counts only, no log text, so the advisor still sees only the report.

## Insights accuracy

### Stop one long-lived session from setting the session duration median
- Status: open

S1 (session duration, median) was 11,623 minutes in dividend-growth and 11,658 in investment for 2026-W46, each from a single session that ran about eight days from its first to its last message, most likely one that was resumed. One such session makes a whole week's S1 meaningless.

Scope: `src/kit/bench/measures.py` (`m_duration`) and whatever computes `minutes(s)`, with UNIT tests. Count active time: sum the gaps between consecutive messages, leaving out any gap over a named constant (`IDLE_GAP_MINUTES = 30`). Note the changed meaning of S1 in `CHANGELOG.md`, because bench and insights tables for older weeks change when re-run.

### Keep loop agents on the applied kit version
- Status: done
- PR: https://github.com/andreas192/claude-kit/pull/16

Both plists still pinned `PYTHONPATH` to `~/.claude/kit/v0.2.0/src`, though both repos recorded v0.4.2. Scheduled runs did reach v0.4.2 through the handover; only a failed handover check left them on the pin. See `docs/reports/2026-11-05-loop-auth-outage.md`.

Nothing re-ran `kit loop install` after 2026-10-26, and `kit apply` asked for it only when migrating off the old loop script. `apply` may not write the plist, so its PR now carries a reminder, and `kit loop status` reports a plist on a different version from the repo.

### Find why scheduled runs lost the Claude login
- Status: blocked
- Blocked by: another occurrence of the expired OAuth session, with its timing recorded
- Depends on: Make a failed loop probe hard to miss

The cause of the 2026-11-03 expiry is unknown, so it may happen again. Scope: when it next happens, compare the time of the first failed probe with the `Claude Code-credentials` Keychain item's modified date and with what other Claude clients were doing. Fix it if the cause is in kit, or document the recovery step in `docs/command.md` if it is not.

### Decide whether the Pro plan covers the loops
- Status: owner
- Blocked by: owner decision on upgrading to Max or reducing how much the loops run

The 2026-11-02 insights report counted 18 runs stopped on usage. On 2026-11-03 runs were stopping at about 80% of the 7-day window. The options are Max, a larger `loop.interval_hours`, or the cheaper stage models the report suggests.

## Loop cost

### Ship the code tasks when only an owner acceptance step is left
- Status: owner
- Blocked by: owner decision on whether a PR may ship with its real-data acceptance left to the owner

Loop worktrees have no `data/` and no access to the real upstream API, so a plan task that needs either cannot run. On 2026-10-30 and 2026-11-02 about 10 build sessions across dividend-growth and investment parked with every code task done and `uv run pytest -q` passing, only because the last task was a real-data acceptance run. The 2026-W44 insights report counted 5 of 9 finished items parked in dividend-growth and 6 of 6 in investment (L3), each after spec and plan were paid for.

Scope: `src/kit/loop/prompts/plan.md` puts steps that need real data, the network or the owner's machine under `## Owner acceptance` in the plan, not as tasks; `build.md` replies `LOOP: ok` when only that section is left; `pr.md` copies it into the PR body. Measure with `kit insights`: parked share and $ per shipped item should fall.
