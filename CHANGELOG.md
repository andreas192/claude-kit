# Changelog

## v0.1.0 — 2026-10-18

Initial release.

- Plugin `kit` with agents `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`.
- `context-warn` hook and test-layer guard hook.
- `kit apply`, `kit bench` and `kit status` CLI.
- Starter files: CLAUDE.md skeleton, `docs/code-conventions.md`, `docs/token-strategy.md`, base permissions.

Same behaviour as dividend-growth's local agents and hooks, except: agents read `test_command` from `.claude/kit.json`; `context-warn` names `docs/token-strategy.md` only when the repo has it, and its env var is `KIT_CONTEXT_WARN_STEP`; the test-layer guard reads `.claude/test-layers.json`, and in investment it no longer denies `import invest.cli_<name>` (the old regex lacked `\b`).
