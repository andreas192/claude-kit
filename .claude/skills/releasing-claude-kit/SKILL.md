---
name: releasing-claude-kit
description: Use when publishing, releasing, cutting, tagging or bumping a new claude-kit version (vX.Y.Z), before running kit apply with a version that has no tag yet.
---

# Releasing claude-kit

## Overview

A release is one commit `chore: release vX.Y.Z` on a `release/vX.Y.Z` branch, merged into `main` through a PR, then tagged `vX.Y.Z` and the tag pushed. `kit apply` snapshots the tag into `~/.claude/kit/vX.Y.Z/` and refuses a snapshot that differs from its tag, so **a tag is immutable once pushed**: never move, delete or reuse it. Fix a bad release with a new patch version.

## Steps

1. **Start clean and current.** On `main`, clean tree, `git pull --ff-only origin main`, then `git switch -c release/vX.Y.Z`. Check that the tag doesn't exist locally or on `origin` (`git ls-remote --tags origin`).
2. **Check what ships.** `git log --oneline $(git describe --tags --abbrev=0)..HEAD`. Every user-visible change needs a bullet under `## Unreleased` in `CHANGELOG.md`. Write any missing bullet in the existing style. If nothing user-visible changed, stop and tell the owner.
3. **Pick the version.** Use the owner's version if they gave one. Otherwise use a minor bump for a new command, flag, loop or insights behaviour, or `kit.json` field, and a patch bump for fixes, wording and docs. State the choice and the reason.
4. **Bump these files, and no others:**

   | File                                | Change                                                                  |
   | ----------------------------------- | ----------------------------------------------------------------------- |
   | `plugin/.claude-plugin/plugin.json` | `"version": "X.Y.Z"`. `apply` rejects a tag whose plugin.json disagrees |
   | `pyproject.toml`                    | `version = "X.Y.Z"`                                                     |
   | `src/kit/__init__.py`               | `__version__ = "X.Y.Z"`                                                 |
   | `tests/test_cli.py`                 | expected `"kit X.Y.Z"`                                                  |
   | `uv.lock`                           | run `uv lock`, never edit by hand                                       |
   | `CHANGELOG.md`                      | `## Unreleased` → `## vX.Y.Z — YYYY-MM-DD` (today)                      |
   | `scripts/apply-kit.sh`              | `version=${2:-vX.Y.Z}` default                                          |
   | `docs/command.md`                   | "version defaults to vX.Y.Z" next to apply-kit.sh                       |

   Any other test that fails on the version string means the test pinned a real version. Change it to a fake one such as `v99.0.0`, as v0.3.0 did in `tests/test_cli_pipeline.py`.
   `plugin.json`, `pyproject.toml`, `__init__.py`, `test_cli.py` and `uv.lock` take `X.Y.Z`. `apply-kit.sh`, `docs/command.md` and `CHANGELOG.md` take `vX.Y.Z`.

5. **Verify.** Run `uv run pytest -q`; it must pass. Run `grep -rnE '\bv?0\.[0-9]+\.[0-9]+' src plugin scripts docs/command.md tests/test_cli.py`. Every hit must be the new version.
6. **Commit and open the release PR.** `git commit -m "chore: release vX.Y.Z"`, `git push -u origin release/vX.Y.Z`, then `gh pr create --base main --title "chore: release vX.Y.Z"`. The body says what ships, lists the bumped files, and has an "After merge" section with the tag step and the apply commands. Don't tag yet, and never push to `main` directly.
7. **Tag after the owner merges.** The owner merges the PR with a merge commit (not squash or rebase, which would rewrite the release commit). Then `git switch main && git pull --ff-only origin main` and check that `git log -1 --format=%s` is `Merge pull request #N from <owner>/release/vX.Y.Z` and that `plugin/.claude-plugin/plugin.json` says `"version": "X.Y.Z"`. Then `git tag vX.Y.Z` (it tags `main`'s HEAD, the merge commit) and `git push origin vX.Y.Z`. Pushing a tag can't be taken back, so ask the owner before pushing unless they already said to publish or push.
8. **Hand over** the apply command: `scripts/apply-kit.sh <investment|dividend-growth> vX.Y.Z`. Don't run it. It is the owner's step, and it never runs from a dividend-growth session against investment.

## Common mistakes

- Editing `uv.lock` by hand, or forgetting it. `uv lock` rewrites it.
- Leaving the default in `apply-kit.sh` at an old version.
- Re-tagging after a fix. Release X.Y.(Z+1) instead.
- Tagging before the release PR is merged, or after someone else's commit landed on `main`: HEAD is then not the release merge. Check the HEAD subject before `git tag`.
- Releasing an `Unreleased` section that doesn't match `git log`, in either direction.
