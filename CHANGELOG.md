# Changelog

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
