# kit v0.4.0: cross-repo roadmap requests

Date: 2026-10-28. Status: draft, for the owner's review. Parents: `2026-10-18-claude-kit-design.md`, `2026-10-24-roadmap-and-loop-design.md`.

## Why

dividend-growth consumes investment's data. Work in dividend-growth regularly confirms an upstream bug or needs a feature from investment. The owner's workflow is: dividend-growth adds an item to investment's roadmap; investment builds it; once done, the owner tells dividend-growth by adding or updating an item on its roadmap.

Agents can no longer take the first step. Three things block it:

1. dividend-growth's CLAUDE.md says "never write to `../investment`", so an interactive session refuses (the kit's own CLAUDE.md constraints repeat the rule).
2. The loop's generated settings turn `loop.forbidden_paths` into `Edit`/`Write` deny rules, and don't-ask mode grants nothing outside the checkout except the scratch folder (`src/kit/loop/settings.py`).
3. Neither the prompts nor any command describe a sanctioned way to file a request.

The owner wants agents, loop and interactive alike, to file cross-repo roadmap items when they confirm an issue or need a feature. They must stay unable to write anything else to another repo.

## Goals

- One sanctioned path for any session to ask another repo for something: a PR on the target repo that adds exactly one item to its `docs/roadmap.md` and changes nothing else.
- The same path for loop and interactive sessions.
- When an agent marks a requested item `done` in its own repo, the owner is told to update the repo that asked.
- Each repo declares which repos it may file requests to; any other target is refused.

## Non-goals

- Agents writing `done` (or any other status change) to another repo's roadmap. The owner does that by hand.
- Merging request PRs automatically. The owner merges them.
- Requests to repos outside the owner's sibling checkouts, or to repos without a kit `docs/roadmap.md`.
- Linking the requester's own items to the request automatically (beyond the PR URL being reported, see below).

## Anti-goals (a failure even if it works)

- Any agent getting `Edit`/`Write` access to another repo's tree. The loop's deny rules for `forbidden_paths` stay exactly as they are.
- A request PR that touches any file other than the target's `docs/roadmap.md`, or changes any existing item.
- Disturbing the target repo's working tree: its checked-out branch, uncommitted changes or index.
- A filed request the target's loop can pick before the owner has read it.
- A request ever reaching `../capital-trading`, or any repo not on the requester's list.

## Constraints

All parent constraints hold. This work changes one of them: `kit request` may, beyond the requester repo, create a temporary git worktree of the **target** repo, commit there, push one branch to the target's `origin` and open one PR on it. It writes nothing else in the target. The kit's CLAUDE.md "Global Constraints" gets a line saying so, and the dividend-growth isolation line becomes "never write to `../investment`, except a roadmap request through `kit request`".

Tests stay offline: `git` on temp repos (a bare repo as `origin`), `gh` through the injected runner.

## Decided

### Roadmap format: a `Requested by` field

`kit/roadmap.py` `FIELDS` gains `Requested by`: optional, any status, value is the requesting repo's directory name (e.g. `dividend-growth`). The starter `docs/roadmap.md` describes it in its fields line. Whatever the requester sends, the target item has `Status: owner` and `Requested by: <requester>` when filed.

### Which repos may file where

A new optional top-level section in `.claude/kit.json`, beside `loop` (interactive sessions use it too):

```json
"requests": {
  "targets": ["../investment"]
}
```

Paths are relative to the repo and resolved. `kit request` refuses a target that is not in the list, has no `.claude/kit.json`, has no valid `docs/roadmap.md`, or whose latest applied kit version (in its `kit.json` on `origin/<base>`) is below v0.4.0: an older parser rejects `Requested by` as an unknown field, so a merged request would stop the target's loop and `kit roadmap`. The refusal says to apply v0.4.0 to the target first. (Today investment is on v0.3.0, so the rollout applies v0.4.0 to investment before dividend-growth sets `requests.targets`.) `kitfile.py` parses and keeps the section like `loop`. A target listed in the requester's `loop.forbidden_paths` is allowed: forbidden paths restrict sessions' file writes, and `kit request` is code, not a session.

### `kit request <requester-repo> <target-repo> <request-file>`

Run as `uv run --project <kit> kit request ...`. The request file is one roadmap item in the standard format: a `### <title>` heading, optional field lines, then the body (what was found, evidence, what is needed). Steps:

1. Read the request. Reject it unless it is exactly one item. Drop any `Status`, `Blocked by` or `Requested by` it gives; set `Status: owner`, `Blocked by: the owner's review of a request from <requester>`, `Requested by: <requester>`. `Depends on` is dropped too: titles in the requester's roadmap mean nothing in the target.
2. Fetch the target's `origin`. The base branch is the target's `loop.base_branch` if it has a `loop` section, else `origin`'s default branch (`git symbolic-ref refs/remotes/origin/HEAD`).
3. Refuse when the title (or its key) already exists in the target's roadmap on that base branch, or an open PR on the target has head `request/<key>`. Print the existing item or PR URL instead.
4. Create a temporary worktree of the target from `origin/<base>` on a new branch `request/<key>`, outside both repos (under `~/.claude/kit/requests/`). The target's own checkout is never touched.
5. Append the item to a `## Requests` section at the end of the target's `docs/roadmap.md`, creating the section if missing. Parse the result; if it does not validate, stop with the errors.
6. Commit only `docs/roadmap.md` (message `roadmap: request from <requester>: <title>`, ending with the co-author line), push `request/<key>`, open a PR on the target against `<base>` titled `request from <requester>: <title>`. The body: the item text, the requester repo and, when run by the loop, the loop branch that filed it.
7. Remove the worktree (also on failure). Print the PR URL.

Errors are `KitError`s with one line each. The command writes nothing in the requester repo.

### Loop sessions

- The prompts' rules line gains: "to ask another repo for a fix or a feature, write one roadmap item per file into `{requests_dir}` (`<scratch>/requests/`); the driver files it as a PR on that repo. Never write to the other repo." The line appears only when the repo's `kit.json` has `requests.targets`, and lists them by name. Each file names its target in its first line `Target: <repo-name>`, so the session doesn't need paths.
- After each stage, the driver files every file in `requests/` through the same code as `kit request` (a shared module, not a subprocess), then deletes it. A failed request (refused, invalid, push failed) does not fail the stage.
- Each outcome is recorded in the runtime state, not on the branch (the PR stage drops `.loop/status.json`): `~/.claude/kit/loop/<repo-name>/requests.json`, keyed by loop branch, each entry `{target, title, url}` or `{target, title, error}`. It survives pauses and later runs.
- Those entries reach the PRs as "Requests filed on other repos" (filed with URL, failed with reason):
  - the parked-PR body, which the driver writes, lists them;
  - the PR stage prompt gets them as a new field `{requests_filed}`, and the session copies them into the body it writes;
  - requests filed during the PR stage itself, after the PR exists, are posted by the driver as a `gh pr comment` on that PR.
- The generated settings don't change: the session already has `Edit` on the scratch folder.
- If the feature can't go on without the requested fix, the stage parks as today (`LOOP: park ...`), and the park reason names the request.

### Interactive sessions

- The starter CLAUDE.md gets one line: "To ask another repo for a fix or a feature, write the item to a file in the scratch folder and run `kit request` (see `docs/command.md`); never edit another repo's files." `docs/command.md` in the kit documents the command.
- Each repo's own CLAUDE.md isolation rule is changed in a session inside that repo (dividend-growth's "never write to `../investment`" gains "except a roadmap request through `kit request`"). `kit apply` lists that line in its PR summary when `requests.targets` is set and CLAUDE.md still has an unqualified "never write to <target>" (prose mention, like v0.1.0's).
- The agent shows the PR URL in its reply.

### Telling the owner when a request is done

- **Loop:** the PR stage session sets `Status: done` itself, so the PR prompt tells it: when the item has `Requested by`, the first line of the PR body is "Requested by <repo>: after merging, update its roadmap." The driver passes the item's `Requested by` value into the prompt (`{requested_by}`, empty when absent) so the session doesn't have to look for it.
- **Interactive:** the starter CLAUDE.md line about landing items gains: "If the item has `Requested by`, tell the owner to update that repo's roadmap."
- **`kit roadmap <repo>`:** the weekend list gains "Tell the requesting repo": every `done` item with `Requested by` whose title does not appear in the requester's `docs/roadmap.md` (read-only, at `../<Requested by>` beside the repo) as a `done` item. The owner clears an entry by adding or updating that item, with the same title, as `done` in the requester. If the requester's roadmap can't be read, the entry is listed with "(requester roadmap not found)".

## Left to the builder

- The module split. Suggested: `kit/request.py` (parse the request, build the item, append and validate: pure), `kit/request_cmd.py` (worktree, commit, push, PR: wiring), shared by the CLI and the driver.
- The exact prompt wording, as long as the rule above is in every stage prompt that has the rules line.
- How the driver passes the runner and `gh` to the shared request code.

## Calls made for the owner

Each can be overturned in review.

- The loop session writes request files and the driver files them. Rejected: giving sessions `gh`/`git` access to the other repo (it widens the loop's permissions; code can guarantee "one roadmap item, nothing else").
- Interactive sessions use the same `kit request` command. (The owner asked for a similar process.)
- Filed items are `Status: owner`. Rejected: `open` (the target's loop could build it before the owner reads it).
- A temporary worktree from the target's `origin/<base>`. Rejected: a branch in the target's checkout (it would disturb whatever the owner has open there).
- Allowed targets in a top-level `requests` section of `kit.json`. Rejected: under `loop` (interactive sessions use it too); reusing `forbidden_paths` (a different meaning).
- Requests go to a `## Requests` section at the end of the target's roadmap. Rejected: letting the requester pick a section (the owner sets priority when reviewing).
- `Requested by` holds the sibling directory name, and the weekend reminder clears by title match in the requester's roadmap. Rejected: a `Requester told` field (one more field to keep by hand).
- `Depends on` is dropped from requests. Rejected: keeping it (titles from the requester don't exist in the target and fail validation).
- Version v0.4.0 (a roadmap format field and a new command).
- `kit request` refuses targets below v0.4.0. Rejected: validating with the target's own kit version (the old parser would refuse every request anyway); relying on the owner to upgrade targets first (a forgotten upgrade stops the target's loop).
- Filed and failed requests are kept in the runtime `requests.json`. Rejected: `.loop/status.json` on the branch (the PR stage deletes it before the PR is written).
- The PR session writes the request list and the "Requested by" line into the body it creates, from prompt fields. Rejected: the driver editing the PR afterwards with `gh pr edit` (the driver would have to parse the roadmap diff, and `gh pr edit` is one more allowed command).

## Rollout

1. Release v0.4.0.
2. Apply v0.4.0 to investment and merge.
3. Apply v0.4.0 to dividend-growth, add `"requests": {"targets": ["../investment"]}` to its `kit.json`, and update its CLAUDE.md isolation line in a dividend-growth session on the apply branch. Merge.
4. Optionally, the same for investment → dividend-growth if investment should file requests too.
