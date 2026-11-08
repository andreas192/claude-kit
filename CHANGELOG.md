# Changelog

## v0.5.1 — 2026-11-08

- `loop.read_first` entries that point outside the repo (such as `../investment/GOLD_SCHEMA.md`) reach loop sessions as absolute paths. Loop sessions run in `.claude/worktrees/feature-loop`, where `../investment` does not exist, so the spec and plan stages could not read the upstream contract: Read reported a missing file and Bash outside the checkout is denied in don't-ask mode. Entries inside the repo stay relative and are read from the worktree. `kit loop run`, `resume` and `install` stop with a `KitError` naming the entry when a `read_first` path does not exist.

## v0.5.0 — 2026-11-08

- `kit` is not on PATH, and sessions in kit repos kept running a bare `kit roadmap .` or `kit request`, failing with exit 127 and searching the docs for the real command. `kit apply` now records `kit_command` (`uv run --project <the kit checkout it ran from> kit`) in `.claude/kit.json`. It rewrites every code span and code-block line that starts with `kit <subcommand>` in the repo's `CLAUDE.md` and top-level `docs/*.md` to that command, and lists each rewritten line in the PR under "Bare kit commands rewritten to the full command". Specs and plans under `docs/superpowers/` are left alone.
- New `kit-command-guard` hook (PreToolUse, Bash): a bare `kit <subcommand>` is denied with the full command from `.claude/kit.json`, so the session retries at once. `kit apply` checks it as `kit-command`.
- The starter files name kit by its full command (`uv run --project ~/Projects/Personal/claude-kit kit ...`), and apply fills in the checkout it runs from. The reminders `kit apply`, `kit loop install` and `kit loop status` print use the full command too.

## v0.4.3 — 2026-11-05

- A `kit loop` run that stops with `env` exits 1, so launchd shows `last exit code = 1`. Every other stop still exits 0, and the agent has no `KeepAlive`, so a failed run waits for its next scheduled hour. A failed probe used to leave launchd at 0 and `launchd.log` empty, which hid a two-day outage.
- A failed probe is kept in `~/.claude/kit/loop/<repo>/probe-failure.txt` with its first failure time and latest reason, until a probe reaches Claude. `kit loop status` and `kit roadmap` start with `loop probe failing since ...` while it lasts. `kit roadmap` gains `--kit-home`.
- `kit apply` reminds in its PR to re-run `kit loop install`, and `kit loop status` adds a `plist:` line when the plist pins a different version from the repo.

## v0.4.2 — 2026-11-02

- `kit loop` sessions load the kit plugin from the running version's snapshot with `--plugin-dir`. `claude -p` never registers the versioned marketplace that `kit apply` declares in `.claude/settings.json`, so since v0.3.2 loop sessions had no `kit:*` agents and the build stage parked after spec and plan were paid for. The probe now stops the run when its session lacks any `kit:*` agent.

## v0.4.1 — 2026-11-02

- `kit loop run` and `kit loop resume` add the loop worktree (`/.claude/worktrees/feature-loop/`) to the repo's local `.git/info/exclude`, even when the worktree already exists. An untracked worktree used to make `kit apply` and `scripts/apply-kit.sh` refuse the repo as dirty, as in investment, whose `.gitignore` doesn't list it.

## v0.4.0 — 2026-11-01

Cross-repo roadmap requests.

- `kit request <requester-repo> <target-repo> <request-file>`: files an item from one repo in another repo's `docs/roadmap.md` as a PR and prints its URL. It works in a temporary worktree of the target under `~/.claude/kit/requests/`, pushes one `request/<key>` branch and opens one PR; the requester and the target's checked-out branch are untouched. The target must run kit v0.4.0 or later. It refuses a target not in `requests.targets`, a request file that is not exactly one `###` item, a title already on the target's roadmap, an open request PR or a `request/<key>` branch already on the target's origin, and a commit that changes anything besides `docs/roadmap.md`.
- `Requested by` field on roadmap items: the filed item carries `Status: owner`, a `Blocked by` line naming the review of the request, and `Requested by: <requester>`. `kit roadmap` adds a "Tell <repo>" line to the owner's weekend list when an item with `Requested by` is done and the requesting repo's roadmap does not show it done yet.
- `.claude/kit.json` gets an optional `requests` section with `targets` (paths such as `../investment`) that `kit request` may file into. `kit apply` keeps it.
- The loop driver files the `<name>.md` request files a session writes to `<scratch>/requests/` after each stage, also when the stage fails, and records them in `~/.claude/kit/loop/<repo>/requests.json`. A failed request never fails the stage. Parked and PR bodies list the requests filed on other repos; requests filed during the PR stage are added as a PR comment.
- `kit apply` adds a note to the PR body for each `CLAUDE.md` line that says "never write to" a request target without naming `kit request`, so the owner can add the exception by hand.
- `starter/CLAUDE.md` tells sessions to ask another repo through `kit request`, and to tell the owner to update the requesting repo's roadmap.

## v0.3.2 — 2026-11-01

- `context-warn` fires once per 60k step (60k, 120k, …), down from 80k. Insights showed sessions often ran past 80k, some to 120k, before handing off, so the earlier warning leaves room to write the handoff before context gets expensive. The starter `docs/token-strategy.md` says ~60k to match. Benchmark B2 still reports the share of sessions over 80k, so results stay comparable across kit versions.

## v0.3.1 — 2026-10-28

- `scripts/apply-kit.sh` defaults to the current version again. v0.3.0 left its default, and the note in `docs/command.md`, at v0.2.0.
- The release checklist is now the project skill `releasing-claude-kit`, linked from `docs/command.md`.

## v0.3.0 — 2026-10-26

Weekly insights.

- The loop driver appends each stage session (cost $, tokens, duration, turns, outcome, model, kit version, session id) and each run's stop reason to `~/.claude/kit/loop/<repo>/stages.jsonl`.
- `kit insights run|install|uninstall`: a weekly report in `~/.claude/kit/insights/<YYYY>-W<ww>.md` for every kit repo under `--base`. It holds the loop's numbers by week and by kit version, and session benchmarks by week and by kit version, with loop sessions left out. Fixed-rule findings follow, then the suggested changes of a read-only Sonnet advisor (`--no-advise` skips it). `install` runs it from launchd on Mondays at 09:00 and shows a notification.

Loop permission fixes.

- The PR stage writes its body to `<temp dir>/kit-loop/<repo>/pr-body.md`, allowed by an `Edit(//…)` rule. Before, it wrote to `~/.claude/kit/loop/<repo>/` under a `Write(//…)` rule, which don't-ask mode denies twice over (`~/.claude` is protected, and `Write` rules grant nothing outside the checkout), so every PR stage parked.
- Every stage prompt now says one Bash command per call, no `cat`/`sed`/`printf`, no `git -C`, with Read and Edit for files. Build sessions had parked when a chained `sed … && git commit` was denied.

## v0.2.0 — 2026-10-24

Roadmap and feature loop.

- `docs/roadmap.md` format: items as `###` headings with `Status`, `Blocked by`, `Depends on`, `Spec`, `Plan` and `PR` fields. `kit roadmap <repo>` validates it and shows the item the loop would pick next, the items it skips and why, and the owner's weekend list.
- `kit loop run|install|uninstall|status|resume`: the feature loop in the kit, run by launchd on weekdays only. The pick is in code (first `open` item in file order with its dependencies done and no `loop/` branch or PR). A spec question the loop cannot answer parks the item as a draft PR with a `## Questions for the owner` section; `resume` hands it back once the owner has answered.
- Each run hands over to a newer applied snapshot. Snapshots now hold `src/kit`, so a scheduled run uses the version the repo applied, not the working tree.
- `kit apply --launch-agents DIR` sets where the loop's launchd plist is written (default `~/Library/LaunchAgents`). `apply` copies a starter `docs/roadmap.md` and removes dividend-growth's feature loop scripts (known hashes), leaving the conversion to the repo.
- `.claude/kit.json` gets an optional `loop` section: `base_branch`, `forbidden_paths`, `read_first`, `pr_checklist`, `interval_hours`.

## v0.1.0 — 2026-10-18

Initial release.

- Plugin `kit` with agents `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`.
- `context-warn` hook and test-layer guard hook.
- `kit apply`, `kit bench` and `kit status` CLI.
- Starter files: CLAUDE.md skeleton, `docs/code-conventions.md`, `docs/token-strategy.md`, base permissions.

Same behaviour as dividend-growth's local agents and hooks, except: agents read `test_command` from `.claude/kit.json`; `context-warn` names `docs/token-strategy.md` only when the repo has it, and its env var is `KIT_CONTEXT_WARN_STEP`; the test-layer guard reads `.claude/test-layers.json`, and in investment it no longer denies `import invest.cli_<name>` (the old regex lacked `\b`).
