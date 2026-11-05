# Loop auth outage, 2026-11-03 to 2026-11-05

Both scheduled loops did no work for two days because the Claude login stopped working. Items for the follow-up work are in `docs/roadmap.md`.

## What happened

- Affected jobs: `com.kit.loop.dividend-growth` and `com.kit.loop.investment`.
- Last good probe: 2026-11-03 10:00.
- Failed runs: 2026-11-03 15:00 to 2026-11-05 10:00, 10 per repo.
- Each run stopped at the probe, in about 0.1 seconds and at $0:

```
probe failed: session failed: Failed to authenticate: OAuth session expired and could not be refreshed
stopped: env
```

An API key was not involved. Kit runs `claude -p`, which uses the claude.ai login stored in the macOS Keychain item `Claude Code-credentials`. `ANTHROPIC_API_KEY` is not set anywhere the jobs would read it.

## Recovery

- The Keychain item was recreated on 2026-11-05 at 10:09 EET. The record does not show what recreated it. Claude Code had updated to 2.1.318 at 10:07.
- At 10:11, `claude -p` with the jobs' `PATH` and an otherwise empty environment returned a normal result.
- A real scheduled run has not been checked since the recovery. The next one was due at 15:00 that day.

## Problems found

1. **The failure was easy to miss.** `driver.py` sends one `osascript` banner on a failed probe, then `guarded()` returns 0 whatever the stop reason. launchd showed `last exit code = 0`, `launchd.log` stayed empty, and the error was only in `~/.claude/kit/loop/<repo>/loop.log`. Whether the banners were delivered from launchd was not checked.
2. **The agents run an old kit.** Both plists still set `PYTHONPATH=~/.claude/kit/v0.2.0/src`, while both repos recorded v0.4.2 on 2026-11-02. The plists were last written on 2026-10-26. **Corrected the same day:** the fixes did reach scheduled runs. Each run on the pinned v0.2.0 driver hands over to the newest snapshot recorded on `origin/develop`, and `stages.jsonl` records v0.4.2 for the runs up to 2026-11-05 15:00. v0.2.0 has no ledger code, so every entry there comes from a later snapshot. The pin matters only when the handover check fails, as it did once on 2026-10-26 with no network. The plists stayed unchanged because nothing re-ran `kit loop install`, not because of unmerged branches: `origin/develop` records v0.4.2 in both repos.
3. **The cause of the expiry is unknown.** No log records why the refresh failed. A refresh token invalidated by another Claude client is a guess, not a finding.
4. **The Pro plan limits the loops.** This did not cause the outage, but the 2026-11-02 insights report counted 18 runs stopped on usage, and on 2026-11-03 runs ended with `stopped: limit` at about 80% of the 7-day window.
