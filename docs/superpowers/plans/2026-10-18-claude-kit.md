# claude-kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task carries a `Model:` tag; route it to the matching implementer agent and never pass `model` when dispatching one.

**Goal:** A versioned Claude Code kit (plugin agents and hooks) that `kit apply` installs into a repo as a frozen snapshot and `kit bench` measures per version from past session transcripts, against a control repo.

**Architecture:** The repo holds a Claude Code plugin (`plugin/`) and a Python CLI (`src/kit/`). `apply` exports a git tag into an immutable local marketplace under `~/.claude/kit/<version>/`, points the target repo's `.claude/settings.json` at it, migrates the repo's local copies away, verifies, records the version in `.claude/kit.json` and opens a PR. `bench` is the former `token_report.py`, extended with windows per applied version, friction, quality and speed measures, and a control repo.

**Tech Stack:** Python 3.12, `uv`, standard library only at runtime (`argparse`, `json`, `hashlib`, `subprocess`), `pytest`; Node for the hooks (`.mjs`); `git` and `gh` as subprocesses.

**Spec:** `docs/superpowers/specs/2026-10-18-claude-kit-design.md` (read its "Builder decisions" section: plugin and marketplace names, measures, migration by known hashes).

## Phases

| Phase | File | Tasks |
|---|---|---|
| 1. Repo and plugin | `2026-10-18-claude-kit/01-plugin.md` | 1–3 |
| 2. `kit bench` and `kit status` | `2026-10-18-claude-kit/02-bench.md` | 4–8 |
| 3. `kit apply` | `2026-10-18-claude-kit/03-apply.md` | 9–14 |
| 4. Release and first rollout | `2026-10-18-claude-kit/04-rollout.md` | 15–16 |

Run the phases in order: `apply` (task 14) uses `write_baseline` (task 8), `kitfile` (task 7) and `gitrun` (task 6). Phase 4 is partly manual (steps marked **Owner**).

## Decisions this plan adds to the spec

- Snapshot and settings layout, names, measures, migration and `applied_at`: spec, "Builder decisions".
- `.claude/kit-bench/baseline.json` is committed with the apply. Dated reports are left untracked; the owner commits one when a result is worth keeping.
- `apply` takes every detected value as a flag too (`--test-command`, `--pipeline-test`, `--wiring-functions`), so a non-interactive run and the tests need no prompts.

## Global Constraints

- No `pip install`, `uv tool install`, `uvx` or `uv pip install --system`. The kit runs as `uv run --project <kit> kit ...` from its own `.venv`. No Homebrew, shell-profile or `podman machine` changes.
- `apply` writes only inside the target repo and inside `~/.claude/kit/`. It never merges a PR. `bench` writes only `.claude/kit-bench/` in the target repo.
- `bench` prints counts and ratios only, never message text.
- Tests run offline with fixtures built in code; `git` runs on temp repos; `gh` and `node` hook runs go through injected runners or real `node` (skip if missing). Never read the real `~/.claude/projects/` in tests.
- Follow `docs/code-conventions.md` (copied from dividend-growth in task 1): minimal functions, typed named results, typed errors (`KitError`), UNIT tests beside each module, PIPELINE tests only in `tests/test_cli_pipeline.py`. `cli.py`, `apply.py` and `bench/run.py` are wiring.
- Plugin name `kit`; marketplace name `kit-v<major>-<minor>-<patch>`; agents `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`.
- Named constants: `MIN_SESSIONS = 5`, `FIX_WINDOW_DAYS = 7`, `DEFAULT_STEP = 80_000` (context-warn), `KIT_HOME = ~/.claude/kit`.
- Never write to `../investment` or `../capital-trading` from a dividend-growth session. Investment is changed only by `kit apply` run by the owner or from a session inside investment.

## Review Focus

1. **Running `apply` twice, or upgrading.** A second `apply` of the same version must stop with "already on vX" and change nothing; an upgrade must replace the old `kit-v*` marketplace entry and `kit@kit-v*` plugin key, not add a second one (tests in tasks 10 and 14).
2. **A snapshot directory that already exists with different content** (someone edited `~/.claude/kit/v0.1.0`): refuse, never overwrite or reuse silently (test in task 9).
3. **A hook that runs in a repo with no `.claude/test-layers.json`**, or a malformed one: the guard allows the write and prints nothing; it must never block every edit (test in task 3).
4. **Transcripts with partial or odd records** (no timestamp, a session that starts before the first apply and ends after it, agent types with a `kit:` prefix): sessions land in the window of their first record and agent types compare without the prefix (tests in tasks 4 and 7).
5. **A repo whose own tests fail before `apply`**: `verify` must report the test command failing and leave the branch without a PR, and the message must say the failure may predate the kit (test in task 13).

---

Execution notes: one `reviewer-sonnet` per batch (up to 3 Sonnet tasks or one Haiku batch); skip review for Haiku batches that only touch docs. A final whole-branch review on Opus runs after task 14.
