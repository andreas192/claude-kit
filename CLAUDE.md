# claude-kit

## Why

The owner's Claude Code setup (agents, hooks, token rules, token benchmarks) grew inside `dividend-growth` and was copied by hand into `investment`. The copies drifted, and there was no way to tell whether a change to the setup made sessions cheaper or smoother. claude-kit is one repo that holds the shared setup and a local pipeline that applies a pinned kit version to a repo (`kit apply`) and benchmarks each repo's past sessions per applied kit version against a control repo (`kit bench`), using only transcripts already on disk.

## Specs and plans

- Spec: `docs/superpowers/specs/2026-10-18-claude-kit-design.md`
- Plan index: `docs/superpowers/plans/2026-10-18-claude-kit.md`
- Spec: `docs/superpowers/specs/2026-10-24-roadmap-and-loop-design.md`
- Plan: `docs/superpowers/plans/2026-10-24-roadmap-and-loop.md`
- Spec: `docs/superpowers/specs/2026-10-25-insights-design.md`
- Spec: `docs/superpowers/specs/2026-10-28-cross-repo-requests-design.md`
- Plan: `docs/superpowers/plans/2026-10-28-cross-repo-requests.md`

## Global Constraints

- No `pip install`, `uv tool install`, `uvx` or `uv pip install --system`. The kit runs as `uv run --project <kit> kit ...` from its own `.venv`. No Homebrew, shell-profile or `podman machine` changes.
- `apply` writes only inside the target repo and inside `~/.claude/kit/`. It never merges a PR. `bench` writes only `.claude/kit-bench/` in the target repo. `insights` writes only `~/.claude/kit/insights/` and reads ledgers, transcripts and git history.
- `bench` and `insights` print counts and ratios only, never message text. The insights advisor sees only that report and the kit's own files.
- Tests run offline with fixtures built in code; `git` runs on temp repos; `gh` and `node` hook runs go through injected runners or real `node` (skip if missing). Never read the real `~/.claude/projects/` in tests.
- Follow `docs/code-conventions.md` (copied from dividend-growth in task 1): minimal functions, typed named results, typed errors (`KitError`), UNIT tests beside each module, PIPELINE tests only in `tests/test_cli_pipeline.py`. `cli.py`, `apply.py` and `bench/run.py` are wiring.
- Plugin name `kit`; marketplace name `kit-v<major>-<minor>-<patch>`; agents `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`.
- Named constants: `MIN_SESSIONS = 5`, `FIX_WINDOW_DAYS = 7`, `DEFAULT_STEP = 60_000` (context-warn), `KIT_HOME = ~/.claude/kit`.
- Never write to `../investment` or `../capital-trading` from a dividend-growth session, except a roadmap request to investment through `kit request`. Investment is changed only by `kit apply` run by the owner or from a session inside investment.
- `request` writes nothing in the requester; in the target it only creates a temporary worktree under `~/.claude/kit/requests/`, pushes one `request/<key>` branch and opens one PR adding one item to `docs/roadmap.md`.

## Working conventions

- **Design as a seasoned developer-tooling engineer from a large engineering org** (the kind who owns the build, release and dev-environment tooling that thousands of engineers depend on). Every brainstorm, spec, plan and review takes this engineer's view and says what it changes:
  - Is the command idempotent and safe to re-run, and does it have a dry-run or preview before it writes anything?
  - Is every input pinned (kit version, tag, plugin and marketplace names), so the same command gives the same result next month?
  - When it fails, does it fail early with a typed `KitError` that names the cause and the next step, and leave no half-applied state behind?
  - Does it stay inside its write boundaries (see Global Constraints), and could a user predict every file it touches?
  - Is the change backwards compatible with repos already on an older kit version, or is the break versioned, written in `CHANGELOG.md` and given a migration path?
  - Can its effect be measured (`kit bench`, `kit insights`) instead of assumed?
  - Prefer boring, explicit, observable behaviour over clever behaviour. Prefer one obvious way to do a thing over flags. Reject features that add magic, hidden state or network calls the user did not ask for.

## Testing

Test command: `uv run pytest -q`

## Commands

Commands live in `docs/command.md`.
