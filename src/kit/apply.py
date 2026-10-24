"""Wiring for `kit apply`: put one kit version into a repo on a branch, check it, commit it, open the PR."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kit import gitops
from kit.bench.run import write_baseline
from kit.detect import Ask, checked_answers, checked_ask, detect, previous_answers, resolve, test_layers_json
from kit.errors import KitError
from kit.gitrun import Runner, require_dir, run_input
from kit.kitfile import Apply, KitFile, read_kitfile, with_apply, write_kitfile
from kit.migrate import HOOK_SCRIPTS, apply_migration, plan_migration, prose_mentions, prose_outside
from kit.settings_edit import read_settings, with_kit, with_permissions, without_hook_scripts, write_settings
from kit.snapshot import PLUGIN_NAME, parse_version, snapshot
from kit.starter import copy_missing, ignore_bench_reports, read_starter
from kit.verify import Check, require_passing, verify

LAYERS_PATH = Path(".claude") / "test-layers.json"


@dataclass(frozen=True)
class ApplyResult:
    branch: str
    commit: str
    pr_url: str | None
    checks: list[Check]


def apply(
    repo: Path,
    version: str,
    kit_repo: Path,
    kit_home: Path,
    answers: dict[str, str],
    ask: Ask | None,
    open_pr: bool,
    known: dict[str, list[str]],
    root: Path,
    run: Runner,
) -> ApplyResult:
    answers, ask = checked_answers(answers), checked_ask(ask)
    parse_version(version)
    repo = require_dir(repo, "repo").resolve()
    if not gitops.is_clean(repo, run):
        raise KitError(f"uncommitted changes in {repo}")
    kit = read_kitfile(repo) or KitFile("", ())
    with_apply(kit, Apply(version, "", ""))
    starter = read_starter(kit_repo, version, run)
    detected = detect(repo)
    resolved = resolve(detected, {**previous_answers(repo, detected), **answers}, ask)
    branch = f"chore/claude-kit-{version}"
    gitops.create_branch(repo, branch, run)

    with gitops.retry_hint_on_failure(branch):
        if not kit.applies:
            write_baseline(repo, root, run, resolved.test_command)
        snap = snapshot(kit_repo, version, kit_home, run)
        migration = plan_migration(repo, known)
        scripts = [s for s in HOOK_SCRIPTS if f".claude/hooks/{s}" in migration.remove]
        settings, removed_hooks = without_hook_scripts(with_kit(read_settings(repo), version, snap), scripts)
        write_settings(repo, with_permissions(settings, starter.permissions))
        layers = test_layers_json(resolved)
        (repo / LAYERS_PATH).write_text(json.dumps(layers, indent=2) + "\n")
        apply_migration(repo, migration)
        added = [str(LAYERS_PATH), *copy_missing(repo, starter.files), *ignore_bench_reports(repo)]

        checks = verify(snap / "plugins" / PLUGIN_NAME, repo, layers, resolved.test_command, kit_home, run_input)
        require_passing(checks, branch)
    commit = gitops.commit_all(repo, f"chore: apply claude-kit {version}", run)
    recorded = Apply(version, commit, gitops.commit_time(repo, commit, run), migration.overrides)
    write_kitfile(repo, with_apply(KitFile(resolved.test_command, kit.applies), recorded))
    gitops.commit_all(repo, f"chore: record claude-kit {version}", run)

    body = gitops.pr_body(version, migration, removed_hooks, added, prose_outside(prose_mentions(repo, run), added), checks)
    url = gitops.open_pr(repo, branch, f"chore: apply claude-kit {version}", body, run) if open_pr else None
    return ApplyResult(branch, commit, url, checks)
