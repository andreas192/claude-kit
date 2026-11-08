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
