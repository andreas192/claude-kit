# claude-kit

Versioned Claude Code setup shared across repos: plugin agents and hooks, applied per repo, benchmarked per version.

The owner's Claude Code setup (agents, hooks, token rules, token benchmarks) grew inside `dividend-growth` and was copied by hand into `investment`. The copies drifted, and there was no way to tell whether a change made sessions cheaper or smoother. claude-kit holds the shared setup in one repo and a local pipeline that applies a pinned kit version to a repo (`kit apply`) and benchmarks each repo's past sessions per applied kit version against a control repo (`kit bench`), using only transcripts already on disk.

## Contents

- `implementer-haiku`, `implementer-sonnet`, `reviewer-sonnet`: plugin agents
- `context-warn` hook: warns when a session's context passes a step
- test-layer guard hook: rules read from the repo's `.claude/test-layers.json`
- token benchmarks: `kit bench`
- roadmap: `docs/roadmap.md`, one format for every repo, checked by `kit roadmap`
- feature loop: `kit loop`, runs roadmap items as draft PRs on weekdays under launchd
- starter files: CLAUDE.md skeleton, `docs/code-conventions.md`, `docs/token-strategy.md`, base permissions (copied by `apply` only where missing)

Agents are `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`.

## Commands

Run from the kit's own `.venv`:

```sh
uv run --project ~/Projects/Personal/claude-kit kit apply <repo> [--version vX.Y.Z]
uv run --project ~/Projects/Personal/claude-kit kit bench <repo> --control <repo>
uv run --project ~/Projects/Personal/claude-kit kit status
uv run --project ~/Projects/Personal/claude-kit kit roadmap <repo>
uv run --project ~/Projects/Personal/claude-kit kit loop run|install|uninstall|status <repo>
```

- `apply` puts a kit version into a repo on a branch and opens a PR. It never merges.
- `bench` prints session counts and ratios per kit version window. It writes only `.claude/kit-bench/` in the target repo.
- `status` shows the kit state of this machine.
- `roadmap` validates the repo's `docs/roadmap.md` and shows what the loop would pick next.
- `loop` runs the feature loop for a repo with a `loop` section in `.claude/kit.json`. See `docs/command.md`.

## Development

```sh
uv sync            # create .venv from the lockfile
uv run pytest -q   # full offline test suite
```

Specs: `docs/superpowers/specs/2026-10-18-claude-kit-design.md`, `docs/superpowers/specs/2026-10-24-roadmap-and-loop-design.md`.
