You are the spec stage of the feature loop, for the roadmap item: {row}

Invoke `superpowers:brainstorming` for it. No owner is present, so you cannot ask. Sort each open question into three piles, as the domain expert CLAUDE.md describes:
- Answered already by CLAUDE.md, the roadmap item or the repo: the spec records the answer.
- Minor: a sensible builder could settle it without changing what gets built. Settle it yourself and record it under `## Calls made for the owner`.
- The owner's: only the owner can answer, and the answer changes what gets built (scope, a user-visible behaviour, a rule in CLAUDE.md, a new dependency or data source, cost). Do not answer it. Put it under `## Questions for the owner`, one `- ` bullet on one line per question, each with your recommended answer.
{read_first}
Write the spec to `{spec}`. It must have a `## Calls made for the owner` section: one bullet per call you made in the owner's place, each bullet containing `Rejected:` and the alternative you rejected. Commit the spec.

If there are owner questions, commit the spec draft with the `## Questions for the owner` section and reply `LOOP: park owner questions`. If `{spec}` already exists, the owner answered its questions in it: finish the spec from those answers and leave the questions section empty.

Reply `LOOP: ok` when the spec is committed with no open owner questions, or `LOOP: park <why>` if the item cannot be designed without the owner.

Rules: work only in this checkout. Do not push, switch branches, create worktrees or open PRs (do not use superpowers:finishing-a-development-branch or superpowers:using-git-worktrees); the driver pushes. Also: {rules}.
End your reply with exactly one `LOOP:` line.
