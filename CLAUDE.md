# claude-kit

## Why

The owner's Claude Code setup (agents, hooks, token rules, token benchmarks) grew inside `dividend-growth` and was copied by hand into `investment`. The copies drifted, and there was no way to tell whether a change to the setup made sessions cheaper or smoother. claude-kit is one repo that holds the shared setup and a local pipeline that applies a pinned kit version to a repo (`kit apply`) and benchmarks each repo's past sessions per applied kit version against a control repo (`kit bench`), using only transcripts already on disk.

## Specs and plans

- Spec: `docs/superpowers/specs/2026-10-18-claude-kit-design.md`
- Plan index: `docs/superpowers/plans/2026-10-18-claude-kit.md`
- Spec: `docs/superpowers/specs/2026-10-24-roadmap-and-loop-design.md`
- Plan: `docs/superpowers/plans/2026-10-24-roadmap-and-loop.md`
- Spec: `docs/superpowers/specs/2026-10-25-insights-design.md`

## Global Constraints

- No `pip install`, `uv tool install`, `uvx` or `uv pip install --system`. The kit runs as `uv run --project <kit> kit ...` from its own `.venv`. No Homebrew, shell-profile or `podman machine` changes.
- `apply` writes only inside the target repo and inside `~/.claude/kit/`. It never merges a PR. `bench` writes only `.claude/kit-bench/` in the target repo. `insights` writes only `~/.claude/kit/insights/` and reads ledgers, transcripts and git history.
- `bench` and `insights` print counts and ratios only, never message text. The insights advisor sees only that report and the kit's own files.
- Tests run offline with fixtures built in code; `git` runs on temp repos; `gh` and `node` hook runs go through injected runners or real `node` (skip if missing). Never read the real `~/.claude/projects/` in tests.
- Follow `docs/code-conventions.md` (copied from dividend-growth in task 1): minimal functions, typed named results, typed errors (`KitError`), UNIT tests beside each module, PIPELINE tests only in `tests/test_cli_pipeline.py`. `cli.py`, `apply.py` and `bench/run.py` are wiring.
- Plugin name `kit`; marketplace name `kit-v<major>-<minor>-<patch>`; agents `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`.
- Named constants: `MIN_SESSIONS = 5`, `FIX_WINDOW_DAYS = 7`, `DEFAULT_STEP = 80_000` (context-warn), `KIT_HOME = ~/.claude/kit`.
- Never write to `../investment` or `../capital-trading` from a dividend-growth session. Investment is changed only by `kit apply` run by the owner or from a session inside investment.

## Testing

Test command: `uv run pytest -q`

## Commands

Commands live in `docs/command.md`.
