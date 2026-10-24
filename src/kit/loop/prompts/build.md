You are the build stage of the feature loop, for the roadmap item: {row}

Execute the next batch of unticked tasks of the plan `{plan}` (spec `{spec}`) per `docs/token-strategy.md`: the `kit:implementer-haiku`, `kit:implementer-sonnet` and `kit:reviewer-sonnet` agents, no `model` parameter, and its batch and escalation rules. Tick the finished tasks in the plan and commit. Run every agent in the foreground (`run_in_background: false`) and never end your turn while one is running: this session exits when your turn ends, so a reply like "running in the background" is your last word and has no `LOOP:` line.

Reply:
- `LOOP: more` if unticked tasks remain;
- `LOOP: ok` when none remain and `{test_command}` passes;
- `LOOP: park <why>` if a task still fails after escalation.

Rules: work only in this checkout. Do not push, switch branches, create worktrees or open PRs (do not use superpowers:finishing-a-development-branch or superpowers:using-git-worktrees); the driver pushes. Also: {rules}.
End your reply with exactly one `LOOP:` line.
