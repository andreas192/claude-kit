# Commands

```sh
uv sync                  # create .venv from the lockfile (dev: pytest)
uv run pytest -q         # full offline test suite
```

The first `uv sync` or `uv run` downloads uv's own managed Python (the repo sets `python-preference = "only-managed"`), so it needs network once.

Run the kit against a repo from its own `.venv`:

```sh
uv run --project ~/Projects/Personal/claude-kit kit apply <repo> [--version vX.Y.Z] [--launch-agents DIR]
uv run --project ~/Projects/Personal/claude-kit kit bench <repo> --control <repo>
uv run --project ~/Projects/Personal/claude-kit kit status
uv run --project ~/Projects/Personal/claude-kit kit roadmap <repo>           # validate docs/roadmap.md, show the next pick and the owner's list
uv run --project ~/Projects/Personal/claude-kit kit loop run <repo> [--pick-only] [--weekend-ok] [--kit-home DIR]
uv run --project ~/Projects/Personal/claude-kit kit loop install <repo> [--launch-agents DIR] [--no-launchctl] [--kit-home DIR]
uv run --project ~/Projects/Personal/claude-kit kit loop uninstall <repo> [--launch-agents DIR] [--no-launchctl] [--kit-home DIR]
uv run --project ~/Projects/Personal/claude-kit kit loop status <repo> [--no-launchctl] [--kit-home DIR]
uv run --project ~/Projects/Personal/claude-kit kit loop resume <repo> <key> [--kit-home DIR]
uv run --project ~/Projects/Personal/claude-kit kit insights run [--base DIR] [--weeks 6] [--no-advise] [--notify] [--kit-home DIR] [--root DIR]
uv run --project ~/Projects/Personal/claude-kit kit insights install|uninstall [--base DIR] [--launch-agents DIR] [--no-launchctl] [--kit-home DIR]
```

To apply a pinned version to `investment` or `dividend-growth` from an up-to-date `develop`, then bench it against the other repo:

```sh
scripts/apply-kit.sh <investment|dividend-growth> [vX.Y.Z] [--no-pr]   # version defaults to v0.2.0
```

It stops on a missing tag, a dirty tree or an existing `chore/claude-kit-<version>` branch.

- `apply --launch-agents DIR`: where the loop's launchd plist goes when the repo has one (default `~/Library/LaunchAgents`).
- `roadmap <repo>`: read-only. Exits 1 with each error's line number when `docs/roadmap.md` does not validate.
- `loop run`: one loop run in the foreground. `--pick-only` prints the pick and stops. `--weekend-ok` lets it run on Saturday or Sunday.
- `loop install|uninstall`: write or remove `com.kit.loop.<repo-name>.plist` and load or unload it with `launchctl`. `--no-launchctl` only writes the file.
- `loop status`: launchd state and the last 20 lines of `loop.log`.
- `--kit-home DIR` defaults to `~/.claude/kit`.
- `loop run --no-handover` is internal: the driver passes it when it re-executes into a newer snapshot.

## Loop

`kit loop` runs the feature loop for a repo that has a `loop` section in `.claude/kit.json` and a `docs/roadmap.md`. Each run takes the first `open` roadmap item, works it on the `loop/<key>` branch in a worktree (spec, plan, build, PR), and opens a PR (a draft only when the item is parked).

Runtime files live in `~/.claude/kit/loop/<repo-name>/`, never in the repo:

- `lock`: held while a run is active. A second run exits at once.
- `loop.log`: the driver's log: each stage, the pick, handovers and stops (`stopped: weekend`, and so on).
- `launchd.log`: stdout and stderr of the scheduled run, for launchd failures.
- `state.json`: the loop's own state between runs.
- `settings.json`: the permissions for `claude -p`, regenerated on each run from the kit's base settings, the repo's `.claude/loop-settings.json` and `forbidden_paths`.
- `note.md`: the note written when no roadmap item is left.
- `note-body.md`: the note as last posted, as a comment on the newest loop PR.

The PR stage session writes its PR body to `pr-body.md` in `<temp dir>/kit-loop/<repo-name>/`, not in the runtime dir: `~/.claude/` is protected in don't-ask mode, and a file outside the checkout is writable only through an `Edit(//<abs path>/**)` rule (a `Write(...)` rule there grants nothing).

The scheduled agent runs on weekdays only, from the applied version's snapshot (`PYTHONPATH=~/.claude/kit/<version>/src`). A foreground `uv run --project <kit> kit loop run <repo>` runs the kit checkout's own code, unless a newer applied snapshot exists, in which case it hands over to that snapshot. To start a run by hand on a weekend, add `--weekend-ok`.

### Resume a parked item

A spec question the loop cannot answer parks the item as a draft PR; `resume` leads to a PR that `gh pr ready` moves out of draft. The PR body and the spec on the loop branch list the questions under `## Questions for the owner`.

1. Answer each question in the spec on `loop/<key>`, so that `## Questions for the owner` is empty. Do it in a separate worktree (`git worktree add ../<key> loop/<key>`), commit and push, then remove it (`git worktree remove ../<key>`). If you used your main checkout, switch it off `loop/<key>` first: `kit loop resume` refuses while any other worktree has the branch checked out.
2. Run `uv run --project ~/Projects/Personal/claude-kit kit loop resume <repo> <key>`. It sets the branch's status back to stage `spec`, commits and pushes. The next weekday run finishes the spec and carries on.

`kit loop resume` refuses while a run holds the lock.

## Insights

`kit insights run` writes `~/.claude/kit/insights/<YYYY>-W<ww>.md` (named for the last complete ISO week) and prints it. For each kit repo under `--base` it shows:

- **Loop by week / by kit version**: runs, stage sessions, shipped, parked, build sessions per shipped item, errors, stops on usage, $ per stage, $ per shipped item, the spec + plan share of $, and median stage peak context. All of it comes from `stages.jsonl`, so loop numbers start with the first run on a version that writes it.
- **Sessions by week / by kit version**: bench's B/F/S/Q4 rows over interactive sessions, with the loop's own sessions left out.
- **Findings**: L1-L7 (loop) and S1-S6 (sessions) rules on the latest week, each with its numbers and one suggested change. Thresholds are in `src/kit/insights/findings.py`.
- **Suggested changes**: a read-only Sonnet session (Read/Grep/Glob, cwd the kit repo) reads the report and the kit's prompts, agents, hooks and token rules, and proposes up to 8 changes. Each cites a number. It costs about $0.20; `--no-advise` skips it.

`kit insights install` writes `~/Library/LaunchAgents/com.kit.insights.plist`. It runs the kit checkout (not a snapshot) on Mondays at 09:00 with `--notify`, and logs to `~/.claude/kit/insights/launchd.log`.

## Release

1. Bump the version in `plugin/.claude-plugin/plugin.json`, `pyproject.toml` and `src/kit/__init__.py`. Then run `uv lock` to refresh `uv.lock`.
2. Commit, then `git tag vX.Y.Z`.
