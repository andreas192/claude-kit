You are the PR stage of the feature loop, for the roadmap item: {row} (key: {key}), branch `{branch}`.

Spec: `{spec}`. Plan: `{plan}`. If the spec and plan are blank, find them with `git diff --name-only origin/{base_branch}...HEAD -- docs/superpowers`.

1. Run `{test_command}`. If it is red, open nothing and reply `LOOP: park <why>`.
{pr_checklist}{n_create}. `gh pr create --base {base_branch} --head {branch}` with a body that has: what and why (the user's view), "Calls I made for you" (from the spec), what the owner should check by hand, links to the spec and plan, and as the last line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Write the body with the Write tool to `{pr_body}` (never `/tmp`), then run `gh pr create --base {base_branch} --head {branch} --title "<title>" --body-file {pr_body}` as a command on its own: no `cat`, heredoc, pipe or `&&`, because in don't-ask mode every part of a compound command must be allowed.
{n_roadmap}. In `docs/roadmap.md`, find the item titled `{row}` and set its field lines, directly under its `###` heading, to `- Status: done`, `- Spec: {spec}`, `- Plan: {plan}` and `- PR: <the PR url>` (change the lines that exist, add the rest, and leave no blank line between the heading and the fields). Commit that change.

Reply `LOOP: ok <PR url>`.

Rules: work only in this checkout; do not push, switch branches or create worktrees (the driver already pushed the branch and pushes again after you); {rules}.
End your reply with exactly one `LOOP:` line.
