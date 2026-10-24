You are the spec stage of the feature loop, for the roadmap item: {row}

Invoke `superpowers:brainstorming` for it. No owner is present: answer every question yourself with your own recommendation, as the domain expert CLAUDE.md describes. Skip the builder check's owner round and fold any "theirs" questions into calls.
{read_first}
Write the spec to `{spec}`. It must have a `## Calls made for the owner` section: one bullet per call you made in the owner's place, each bullet containing `Rejected:` and the alternative you rejected. Commit the spec.

Reply `LOOP: ok` when the spec is committed, or `LOOP: park <why>` if the item cannot be designed without the owner.

Rules: work only in this checkout. Do not push, switch branches, create worktrees or open PRs (do not use superpowers:finishing-a-development-branch or superpowers:using-git-worktrees); the driver pushes. Also: {rules}.
End your reply with exactly one `LOOP:` line.
