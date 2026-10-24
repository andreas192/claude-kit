# kit v0.2.0: a standard roadmap and the feature loop in the kit

Date: 2026-10-24. Status: draft, for the owner's review. Parent: `2026-10-18-claude-kit-design.md`.

## Why

The two repos plan work in incompatible shapes. dividend-growth keeps a spec file of tables (`docs/superpowers/specs/2026-10-05-dgi-roadmap.md`: `Item | Why deferred | Depends on` under several headings, "done" written into a cell) plus `docs/next-steps.md`. investment keeps a master plan of waves and stages (`docs/superpowers/plans/2026-10-05-roadmap-master-plan.md`) plus a sketch with a "Proposed order" table, and records status as prose. The owner meant to keep one format; features kept landing and the formats drifted. The owner now wants one format that both repos use.

The feature loop (`dividend-growth/scripts/feature_loop.py`, run every 5 hours by launchd) turns roadmap items into PRs, one `claude -p` session per stage. The parent spec left it out of the kit because it is tied to dividend-growth's roadmap layout. A standard roadmap removes that tie, so the loop moves into the kit and any kit repo can run it.

## Goals

- One roadmap file, at one path and in one format, that people, Claude sessions and the loop all read and update the same way.
- `kit roadmap <repo>` checks the file and shows what the loop would pick next, and why it skips each other open item.
- `kit loop` runs the loop for any kit repo, using that repo's settings from `.claude/kit.json`, at the kit version the repo has applied.
- dividend-growth's loop moves to the kit without losing in-flight work: the existing `loop/*` branches and their `.loop/status.json` resume.

## Non-goals

- Converting the existing roadmaps automatically. They are free prose; each repo converts its own in a session inside that repo, where CLAUDE.md and the isolation rules apply.
- Running the loop in investment as part of this work. investment gets the roadmap format now; whether its loop is installed is the owner's call later (see Rollout).
- Separating loop sessions from interactive ones in `kit bench`.
- A scheduler other than macOS launchd.
- Per-repo stage models. Models and effort per stage are part of the kit version, so a change to them shows up as a kit window in `kit bench`.

## Anti-goals (a failure even if it works)

- The loop running code from the kit's working tree. Editing the kit must change no repo's loop until a new tag is applied (same rule as the plugin).
- A loop that picks an item the owner marked blocked or is working on.
- Losing or restarting an in-flight loop branch because the roadmap moved.
- The loop writing outside its checkout, or to a path the repo forbids (`../investment` and `../capital-trading` from dividend-growth).

## Constraints

All of the parent spec's constraints still hold, plus:

- `kit loop install` and `kit loop uninstall` may also write `~/Library/LaunchAgents/com.kit.loop.<repo-name>.plist` and call `launchctl` for that label only. Nothing else in the kit touches launchd.
- The loop's runtime files (lock, log, state, generated settings) live in `~/.claude/kit/loop/<repo-name>/`, never in the repo's tracked tree.
- The loop driver uses the standard library only and runs pinned from `~/.claude/kit/<version>/`, with `uv run --no-project python ...`. No installs.
- Tests stay offline: no real `claude`, `gh`, `launchctl` or `osascript`; the driver's `Env` injection (as in dividend-growth's `tests/test_feature_loop.py`) carries over.

## Decided

### The roadmap format

Path: `docs/roadmap.md` in every kit repo. Fixed, not configurable.

```markdown
# Roadmap

(free intro: scope, how to add an item)

## Features

### Valuation against the company's own history
- Status: open
- Depends on: Two-stage dividend discount model

P/E and P/FCF against the company's own 10-year median ...

### Host port for the UI
- Status: blocked
- Blocked by: owner decision; needs a port mapping in investment's cluster.tf

### Dividend pay dates and calendar
- Status: done
- Spec: docs/superpowers/specs/2026-10-18-dividend-pay-dates-and-calendar-design.md
```

Rules:

- `## ` headings are sections with any name (e.g. Features, Scoring review, Known data bugs, Housekeeping). The order in the file is the priority order.
- Each `### ` heading is one item. Its title is unique in the file. The item's key is the title lowercased, with runs of non-alphanumerics turned into `-`, cut to 50 characters at a `-` (dividend-growth's `item_key`, unchanged). The loop's branch is `loop/<key>`.
- Right after the heading come field lines `- Name: value`, ending at the first line that is not a field. After that, the item's body is free Markdown up to the next heading.
- Fields:

| Field | Required | Values |
|---|---|---|
| Status | yes | `open` (ready; the loop may take it), `active` (someone is working on it outside the loop), `blocked`, `done`, `dropped` |
| Blocked by | when `blocked`, and only then | free text: the decision, input or upstream data it waits for |
| Depends on | no | comma-separated item titles from the same file |
| Loop | no | `no`: ready, but the owner wants to do it in person |
| Spec, Plan, PR | no | a path or URL. Set when the work starts or lands |

- Validation errors: an unknown field, a missing or unknown Status, `Blocked by` missing on a blocked item or present on any other, a duplicate title or key, a `Depends on` title that is not in the file.
- Whoever lands an item sets `Status: done` and fills in Spec, Plan and PR in the same PR: the loop's PR stage, or the owner's session. The starter CLAUDE.md says so in one line.

### `kit roadmap <repo>` (read-only)

It validates `docs/roadmap.md` and prints, as counts and titles only:

- the number of items per status,
- the item the loop would pick next, given the repo's `loop/*` branches and PRs (`gh pr list`, through the injected runner),
- each open item it would skip, with the reason: `taken by <PR url or branch>`, `depends on <title> (<status>)`, `Loop: no`.

It exits 1 with each error's line number if the file does not validate.

### The pick becomes deterministic

dividend-growth's pick stage is a Sonnet session that reads the roadmap and judges what is blocked. With explicit statuses the driver picks in code: the first item in file order that has `Status: open`, no `Loop: no`, every `Depends on` item `done`, and no `loop/<key>` branch or PR in any state. This saves one session per run and makes `kit roadmap` show exactly what the loop will do.

What the LLM used to judge ("needs upstream data not in GOLD_SCHEMA.md", "needs the cluster or Terraform") becomes `Status: blocked` with a `Blocked by` line, set when the roadmap is converted or the item is added. The spec stage can still park an item it finds it cannot design. The parked draft PR keeps the item taken, as today.

When no item is left, the driver writes the note itself from the roadmap and the PR list: the blocked items with their `Blocked by`, the `Loop: no` items, and the parked and waiting loop PRs by URL. It posts the note as dividend-growth's loop does today: a comment on the newest loop PR, or a notification when there is none, and only when the note changed.

### The loop in the kit

The stage machine, status file, PR handling, usage limits and failure policy carry over from `dividend-growth/scripts/feature_loop.py` unchanged in behaviour, except for the deterministic pick and the parameters below. These stay as they are, so in-flight branches resume:

- the `loop/` branch prefix and key rule,
- `.loop/status.json` on the branch, with the same fields,
- the spec and plan paths `docs/superpowers/{specs,plans}/<date>-<key>...`,
- the `## Calls made for the owner` gate before the PR stage,
- the stage list (`spec`, `plan`, `build`, `pr`) and the `LOOP:` reply protocol (no `pick` reply any more),
- the worktree `.claude/worktrees/feature-loop`.

The prompts become kit templates. Everything specific to dividend-growth moves into a `loop` section of `.claude/kit.json`:

```json
"loop": {
  "base_branch": "develop",
  "forbidden_paths": ["../investment", "../capital-trading"],
  "read_first": ["../investment/GOLD_SCHEMA.md"],
  "pr_checklist": [
    "Update docs/how-to-guide.md if the feature changes anything CLAUDE.md lists for it (screen, filter, metric, band, flag, profile, default, workflow), including its \"Last reviewed\" line, and commit."
  ],
  "interval_hours": 5
}
```

| Key | Required | Used for |
|---|---|---|
| `base_branch` | yes | worktree base, branch base, PR base, the roadmap the pick reads (`origin/<base>:docs/roadmap.md`) |
| `forbidden_paths` | no (default none) | the "never write" rule in every prompt, and `Edit`/`Write` deny rules in the generated settings, resolved to absolute paths |
| `read_first` | no | files the spec stage reads before designing (replaces `{gold_schema}`) |
| `pr_checklist` | no | extra numbered steps in the PR stage, between the test run and `gh pr create` |
| `interval_hours` | no (default 5) | launchd `StartInterval` |

In the prompts, "the expert dividend growth investor of CLAUDE.md" becomes "the domain expert CLAUDE.md describes", and "the investor view" becomes "the user's view". Each prompt that runs tests uses `test_command` from `kit.json`.

`kitfile.py` reads and writes the `loop` section. `write_kitfile` must keep it (today it rewrites only `test_command` and `applies`).

### Permissions for loop sessions

The loop runs `claude -p --permission-mode dontAsk --settings <file>`. The driver generates that file into `~/.claude/kit/loop/<repo-name>/settings.json` on each run, by merging:

1. the kit's base loop permissions (`starter/loop-settings.json`, read from the version tag): Read/Glob/Grep, `Edit(./**)`, `Write(./**)`, Agent, Skill, TodoWrite, `git status|diff|log|show|add|commit|rm|rev-parse`, `gh pr create|view|list`, `ls|grep|head|tail|wc`, the repo's `test_command`; deny `git push`, `git checkout|switch|worktree`, `gh pr merge|close`, `gh api`, `gh repo`, force pushes, `pip`, `uv pip`, `uv tool`, `brew`, `podman`, `docker`;
2. the repo's own `.claude/loop-settings.json`, if it exists (dividend-growth's adds e.g. `Bash(uv run dgi *)` and its script denies);
3. `Edit(<abs>/**)` and `Write(<abs>/**)` deny rules for each `forbidden_paths` entry.

Allow and deny lists are unioned, and deny wins. This replaces `feature_loop.sh`'s `sed` over relative sibling paths, which was needed because the worktree sits two levels below the repo.

### Pinned version and scheduling

- `kit apply` exports the tag's `loop/` folder (driver and prompts) into the snapshot `~/.claude/kit/<version>/loop/`, beside the plugin marketplace. The snapshot stays immutable.
- `kit loop install <repo>` needs a `loop` section and a valid roadmap. It writes `com.kit.loop.<repo-name>.plist`, which runs the snapshot's driver for the repo's latest applied version, and loads it. It refuses while another launchd agent in `~/Library/LaunchAgents` runs a loop for the same repo path (dividend-growth's `com.dgi.feature-loop`), and says which command removes it.
- Each run, the driver reads `.claude/kit.json` on `origin/<base_branch>`. If its latest version is newer than the running driver's and that snapshot exists, it hands over to that driver for the run. A new kit version therefore reaches the loop when its apply PR merges, the same moment `kit bench` starts the new window.
- `kit loop uninstall <repo>`, `kit loop status <repo>` (launchd state plus the last 20 log lines) and `kit loop run <repo> [--pick-only]` (one run in the foreground; `--pick-only` prints the pick and stops) complete the command.
- Notifications are titled `kit loop: <repo-name>`.

### Migration in `kit apply`

- Starter files, copied only where missing: `docs/roadmap.md` (intro text and the format above, no items), and one line in the starter CLAUDE.md pointing at it.
- Known-hash removal (same mechanism as v0.1.0) of dividend-growth's `scripts/feature_loop.py`, `scripts/feature_loop.sh`, `scripts/loop_prompts/*.md` and `tests/test_feature_loop.py`. `.claude/loop-settings.json` stays: it becomes the repo's addition to the base permissions.
- The PR summary, beside the prose lines v0.1.0 already lists:
  - the roadmap files found (files named `*roadmap*` under `docs/`, plus `docs/next-steps.md`) as "to convert into docs/roadmap.md",
  - when a loop launchd agent for the repo is loaded: "before merging, run `scripts/feature_loop.sh uninstall` in the repo; after merging, `kit loop install <repo>`",
  - a missing `loop` section, when the repo had a loop.

### Converting each repo's roadmap

Done once per repo, in a session inside that repo, on the apply branch before merge (dividend-growth) or its own branch (investment):

- Every open, active and blocked item from the old files becomes an item. Done items get one line each with their links, so the history stays readable; long research tables stay in their spec and the item links to them.
- **Titles of items with a `loop/*` branch keep the old first-cell text exactly**, so their keys, and so their branches and PRs, still match. On 2026-10-24 those are the 7 branches under `loop/` in dividend-growth (automatic classification, backtesting, dividend pay dates, holdings and income projection, regime or beta, two-stage DDM, valuation against own history).
- What the old pick prompt judged as blocked becomes `Status: blocked` with a `Blocked by` line.
- The old files are replaced by a one-line pointer to `docs/roadmap.md`, so links in specs keep working. CLAUDE.md and `docs/command.md` point to the new file.
- `kit roadmap <repo>` passes before the branch is merged.

## Rollout

1. Build v0.2.0 with the loop's behaviour unchanged apart from the deterministic pick and the parameters above.
2. dividend-growth: apply v0.2.0, convert the roadmap on the apply branch, add the `loop` section, run `kit roadmap`, run `scripts/feature_loop.sh uninstall`, merge, then `kit loop install`. Check the first run in `kit loop status`: it resumes an in-flight `loop/*` branch rather than picking a new item.
3. investment: apply v0.2.0 (it moves from no kit, or v0.1.0, straight to v0.2.0), convert the master plan and sketch into `docs/roadmap.md` in an investment session, and run `kit roadmap`. Installing its loop needs a `loop` section and a review of its `guard.mjs` rules against unattended sessions; that is a separate decision for the owner.

## Left to the builder

- The module split. Suggested: `kit/roadmap.py` (parse, validate, pick: pure functions), `loop/driver.py` (stdlib only, ported with its tests), `kit/loop_cmd.py` (install, uninstall, status; wiring).
- How the driver hands over to a newer snapshot (re-exec, or launching it as a subprocess).
- The wording of the kit's prompt templates, as long as the rules above appear in each one.
- How `kit roadmap` reports when `gh` is unavailable (it can still validate and list statuses).

## Calls made for the owner

The owner skipped the questions. Claude made these calls; each can be overturned in review.

- One fixed path, `docs/roadmap.md`. Rejected: a path set in `kit.json` (a standard that each repo can relocate is not a standard).
- Items as `###` headings with field lines. Rejected: one table per section (dividend-growth's cells already run to several hundred characters, and a table has no room for detail).
- A deterministic pick in code. Rejected: keeping the Sonnet pick session (a cost on every run, and its judgement of "blocked" cannot be checked in advance).
- The `active` status and the `Loop: no` field. Rejected: inferring "someone is on it" from branch names (an owner branch such as `feat/cash-flow-coverage` does not name the item).
- Stage models fixed per kit version. Rejected: per-repo overrides in `kit.json` (they would change loop cost without a kit window in `kit bench`).
- Runtime files in `~/.claude/kit/loop/<repo-name>/`. Rejected: `data/loop/` (repo-specific; investment's `data/` holds the warehouse).
- investment gets the format now and the loop later. Rejected: installing its loop in this rollout (its guard hook and isolation rules were written for attended sessions).
