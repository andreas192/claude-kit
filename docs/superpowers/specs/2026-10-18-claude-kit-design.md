# claude-kit: a shared Claude Code setup, applied per repo and benchmarked per version

Date: 2026-10-18. Status: approved 2026-10-18. Plan: `docs/superpowers/plans/2026-10-18-claude-kit.md`.

## Why

The owner's Claude Code setup (agents, hooks, token rules, token benchmarks) grew inside `dividend-growth` and was copied by hand into `investment`. The copies have drifted. `investment`'s implementer agents are the older one-task version, with no `effort` or `tools` fields. Improvements made in one repo never reach the other. There is also no way to tell whether a change to the setup made sessions cheaper or smoother.

claude-kit is one repo that holds the shared setup and a local pipeline that:

1. **applies** a pinned kit version to a repo on this machine, adapted to that repo's language and layout, and
2. **benchmarks** each repo's past sessions grouped by the kit version that was active, using only the session transcripts already on disk (no paid runs).

## Goals

- `kit apply <repo>` puts a chosen kit version into a repo: it detects the details, writes the config, checks that the hooks work and opens a PR. Running it again with a newer version upgrades the repo.
- Each repo keeps local changes on top of the kit and stays readable without the kit (plain files in `.claude/`).
- `kit bench <repo>` reports token, friction, agent and quality numbers for each kit-version window and the difference between consecutive windows, against a control repo.
- A kit change applied to one repo reaches no other repo until it is applied there too. This keeps the control repo clean.

## Non-goals

- Paid controlled runs (A/B runs on fixed tasks with `claude -p`). The owner chose free numbers from past sessions only.
- Language packs for stacks no repo uses yet. Only Python + uv now (`dividend-growth`, `investment`). Add `node-ts` or `go` when a repo in that language adopts the kit.
- An LLM step in `apply`. Detection is deterministic. CLAUDE.md architecture text is written by hand in a session in the target repo.
- Moving `feature_loop` into the kit. It is tied to dividend-growth's roadmap and plan layout. Revisit when a second repo wants it.
- Syncing or pushing from one repo into another.

## Anti-goals (a failure even if it works)

- Any kit change that silently reaches every repo at once, e.g. agents in `~/.claude/agents/`, or a plugin loaded from a live, editable folder. Benchmark windows would lie.
- `apply` overwriting the owner's existing CLAUDE.md, permissions or local hooks without showing it in the PR diff.
- A benchmark that gives a verdict on too few sessions.
- Breaking a repo's isolation rules. `dividend-growth` forbids writes to `../investment` and `../capital-trading` from its sessions.

## Constraints

- The owner's isolation rules apply. No `pip install`, `uv tool install`, `uvx` or `uv pip install --system`. The kit's Python runs from its own `.venv` (`uv run --project <kit> kit ...`). No Homebrew, shell-profile or `podman machine` changes.
- `apply` is run by the owner in a terminal, or from a Claude session inside the target repo. Never from a session in another repo.
- `apply` writes only inside the target repo and inside `~/.claude/kit/` (version snapshots, see below). It never merges a PR.
- `bench` is read-only: it reads `~/.claude/projects/` transcripts and the repo's git history and writes only its report into the target repo.
- Tests run offline, with fixtures built in code. This follows dividend-growth's conventions: minimal functions, the UNIT vs PIPELINE layers of `docs/code-conventions.md`, and TDD.

## Decided

### What the kit contains

| Part | Source today | Delivered as |
|---|---|---|
| `implementer-haiku`, `implementer-sonnet`, `reviewer-sonnet` | dividend-growth's batched versions (the owner's call: these become the shared ones) | plugin agents |
| `context-warn` hook | `dividend-growth/.claude/hooks/context-warn.mjs` | plugin hook |
| test-layer guard | `test-layer-guard.mjs` in both repos | plugin hook, rules read from the repo's `.claude/test-layers.json` |
| token benchmarks | `dividend-growth/scripts/token_report.py` | kit CLI (`kit bench`), extended |
| starter files: CLAUDE.md skeleton, `docs/code-conventions.md`, `docs/token-strategy.md`, base permissions | dividend-growth | copied by `apply` only where the file is missing |

Per repo, not in the kit: CLAUDE.md content, isolation rules, permissions, repo-specific hooks (e.g. `investment/.claude/hooks/guard.mjs`) and `feature_loop`.

### Making the shared parts generic

- The agents name no test command. They read it from the repo: "run the test command in CLAUDE.md (section Testing) on the task's test files only". The builder may choose a different fixed place, such as a `test_command` key in `.claude/kit.json`, but agents must not hard-code `uv run pytest`.
- `context-warn` loses the `dgi-` prefix in its state file and the `DGI_` prefix in its env var. It points at the repo's `docs/token-strategy.md` only if that file exists.
- The test-layer guard keeps its behaviour and takes its project-specific parts from `.claude/test-layers.json`: the pipeline test path, the package name and the wiring function names. The two current regexes (`dgi`/`run_refresh`, `invest`/`run_all`) must come out of that file unchanged in effect.

### Version pinning, so windows are exact

- A kit version is a git tag (semver) of the claude-kit repo.
- `apply` exports that tag into an immutable snapshot `~/.claude/kit/<version>/`, if it isn't there yet. The snapshot is a local plugin marketplace with the plugin inside.
- The repo's `.claude/settings.json` points `extraKnownMarketplaces` at that snapshot path and enables the plugin in `enabledPlugins`. Editing the kit's working tree therefore changes no repo. Only a new tag plus `apply` does.
- Plugin agents are namespaced (`<plugin>:implementer-haiku`). `apply` updates the repo's agent references, such as `docs/token-strategy.md` "Model routing", or the builder keeps short names by another means. Either way, plans must still route by model as they do today.

### `kit apply <repo> [--version vX.Y.Z]`

Default version: the latest tag.

1. **Pre-check.** The repo is a git repo with no uncommitted changes. The script creates the branch `chore/claude-kit-<version>`. If any check fails, it stops with a clear message.
2. **Baseline (first apply only).** It saves the repo's current benchmark numbers to `.claude/kit-bench/baseline.json`, so later numbers can be read against them even if transcripts are deleted.
3. **Detect.** It reads `pyproject.toml` (package name, test runner), `uv.lock`, the tests folder layout and the CLI or pipeline entry points. It proposes values for `.claude/test-layers.json` and the test command. Anything it can't decide, it asks for interactively, and it accepts answers as flags for re-runs. Unsupported stack: stop and say which pack is missing.
4. **Apply.**
   - Snapshot as above.
   - Edit `.claude/settings.json` as JSON, never as text: add the marketplace and plugin, and leave the owner's permissions and other hooks as they are.
   - Write `.claude/test-layers.json`.
   - **Migrate.** Remove local copies that the plugin now provides, such as `.claude/agents/implementer-*.md`, `reviewer-sonnet.md`, `.claude/hooks/test-layer-guard.mjs`, `context-warn.mjs` and their `settings.json` hook entries. Otherwise hooks run twice and local agents override the plugin's. A local file that differs from the kit's version is kept, and the summary reports it as a local override.
   - Copy starter files only where missing.
5. **Verify.**
   - The settings JSON parses.
   - Each plugin hook runs on sample inputs and gives the expected allow or deny. For the guard, this uses a wiring test outside the pipeline file plus the pipeline file itself.
   - Agent frontmatter is valid.
   - The repo's own test command passes.
   - If anything fails, it leaves the branch for inspection and prints what failed. No PR.
6. **Record.** It appends `{version, commit, applied_at (UTC)}` to the `applies` list in `.claude/kit.json`. It never rewrites earlier entries.
7. **Commit and open a PR** with `gh pr create`. The body includes the summary: files added, removed and kept as overrides. The owner merges.

`applied_at` is the moment the version takes effect for benchmarking. The builder decides whether this is the commit time or the merge time; merge time is more accurate, and `kit bench` may resolve it from git.

### `kit bench <repo> [--control <repo>] [--since ...]`

- **Windows.** "pre-kit" runs from the first transcript to the first apply. Then there is one window per entry in `applies`, from its `applied_at` to the next one. A session belongs to the window its first record falls in.
- **Control.** The same time boundaries are applied to the control repo's sessions. A change that shows in both repos is not the kit's doing. The default control is the other kit repo if one exists; a repo without the kit also works.
- **Output.** A table with one column per window, a Δ column for each pair of consecutive windows, and the control repo's Δ beside it. It is written to `.claude/kit-bench/<date>.md` and printed.
- **Too little data.** If a window has fewer than 5 sessions (builder may tune the threshold), its Δ cells say "not enough data" and give no number.
- **Data sources.** Transcripts in `~/.claude/projects/` (worktrees included, as `token_report.py` does today) and the repo's git history. Counts and ratios only, never message text.

Measures:

| Area | Measures |
|---|---|
| Tokens and cost | B1–B13 as defined in `dividend-growth/docs/token-strategy.md` "Benchmarks", same cost proxy |
| Friction | permission prompts or rejections per session, hook denials per session, context-warn firings per session |
| Agent behaviour | tasks per implementer, reviewers per batch, Opus subagents, search subagents (B8–B11) |
| Quality | reviewer findings per batch, re-reviews per batch, failing test runs before a pass, PRs reverted or followed by a fix to the same files within 7 days (from git) |
| Speed | session duration, owner prompts per finished task |

Before building a friction or quality measure, check that the transcripts record what it needs. Drop a measure that can't be read reliably, and list it in the report as "not measured". Never estimate one.

### Repo layout and tooling

- Python 3.12 with `uv`, CLI entry point `kit`, offline `pytest`. The hooks stay in Node (`.mjs`), as today.
- `token_report.py` moves into the kit as the base of `kit bench`. dividend-growth's copy is removed by `apply`'s migration once the kit version that contains it is applied. dividend-growth's `docs/command.md` then points to `kit bench`.
- `kit status` (read-only) lists the repos found under `~/Projects/Personal/` that have `.claude/kit.json`, with their current version and any local overrides.

## Left to the builder

- The CLI library (argparse or typer) and the module split.
- How detection finds the wiring entry points for a Python repo.
- The plugin's internal layout and manifest details, checked against the current Claude Code plugin docs.
- Whether `applied_at` comes from the commit time or the merge time.
- How plugin agent names are mapped in each repo.
- The exact transcript fields behind each friction and quality measure.
- The thresholds, as long as they are named constants.

## First rollout

Why the order matters: a change in the numbers can come from the kit or from something outside it (a new model, a Claude Code update, a different kind of work that week). A control repo that did not change over the same dates shows the outside effect, so it can be told apart from the kit's.

1. Build kit v0.1.0 with the content extracted from dividend-growth unchanged in behaviour.
2. Apply it to `dividend-growth` and run `kit bench dividend-growth --control ../investment`. Investment has no kit yet, so it is a clean control. Because v0.1.0 changes nothing in how dividend-growth behaves, its first Δ should be close to zero: it checks the measuring, not the kit.
3. After at least 5 dividend-growth sessions on v0.1.0, apply it to `investment`. Its implementer agents then change from the one-task version to the batched version, and its own benchmark shows the effect, with dividend-growth as its control as long as dividend-growth gets no newer kit version in that window.

## Builder decisions (2026-10-18, from the plugin docs and the transcripts on disk)

- **Names.** Plugin `kit` (names starting with `claude-` are reserved by the plugin validator). One marketplace per version, named `kit-v0-1-0` for `v0.1.0`, because Claude Code registers marketplaces by name for the whole user: two repos on different versions must not share a name. Agents are therefore `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet` in every repo and every version.
- **Snapshot.** `~/.claude/kit/<version>/` holds `.claude-plugin/marketplace.json` and `plugins/kit/`. The repo declares it in `extraKnownMarketplaces` as `{"source": {"source": "directory", "path": "<absolute path>"}}`. A local directory marketplace is read in place (not copied to the plugin cache), which is why the snapshot must never change after it is written; `apply` refuses to reuse a snapshot whose content differs from the tag.
- **Test command.** `.claude/kit.json` holds `test_command` (detected, e.g. `uv run pytest -q`). Agents read it from there.
- **`applied_at`.** `apply` records the commit time. `kit bench` uses the time of the first commit on the default branch's first-parent history that contains the entry (the merge), and falls back to `applied_at` while the PR is not merged.
- **Wiring names for the guard.** Detection reads them from the repo's existing `test-layer-guard.mjs` regex when there is one (so `run_refresh` and `run_all` come out unchanged); otherwise it proposes the `run_*` functions of `<package>/pipeline.py` and asks.
- **Migration by known content.** The kit ships the SHA-256 of every local file version it replaces (dividend-growth's and investment's current agents and hooks, and dividend-growth's `scripts/token_report.py` with the tests of the moved files, `tests/test_token_report.py` and `tests/test_context_warn_hook.py`). A local file with a known hash is removed; any other content is kept and reported as an override. Prose that names the old agents or files (CLAUDE.md, `docs/token-strategy.md`, `docs/command.md`) is not rewritten by `apply`: the PR summary lists each file and line, and the owner edits them on the same branch.
- **Measures the transcripts support.** Permission *denials* (tool results starting `Permission for this action was denied` or containing `doesn't want to proceed`); approved permission prompts are not recorded, so "permission prompts" is reported as not measured. Hook denials (tool results matching `^<Event>:<Tool> hook error:`). Context-warn firings (hook attachments whose content starts `Context is `). Failing test runs before a pass (Bash calls whose command contains the repo's `test_command` and whose result is an error). Reviewer findings (numbered lines in a `kit:reviewer-sonnet` or `reviewer-sonnet` agent's last message; `PASS` is zero). Re-reviews (reviewer descriptions containing `re-review`). Session duration (first to last timestamp). Agent types are compared without their plugin prefix.
- **CLI.** `argparse`, standard library only at runtime; `pytest` as the only dev dependency.
