# Token strategy

Each workflow stage ends in a written artifact. The next stage starts in a fresh session (`/clear`) that reads only that artifact, not the chat history.

## Per stage

| Stage | Model / effort | Context rule |
|---|---|---|
| Brainstorm | Opus, high | Reference only the spec. Output is a spec file. |
| Plan | Opus, medium | Read only the spec, not the code. Output is small, independent tasks. |
| Implement | Sonnet or Haiku per task tag, via the implementer agents (see Model routing) | `/clear` per batch. `@` the tasks' files. Read only those tasks' plan sections. |
| Review / debug | Sonnet | Give the diff or failing output only. Use `/rewind`, not `/compact`, after a bad turn. |

Set the model and effort once at session start (`/model`, `/effort`); the table's effort only applies if you set it. Switching mid-session breaks the prompt cache.

The feature loop (`scripts/feature_loop.py`) runs one fresh session per stage with the stage models above.

## Model routing

Opus writes the spec and the plan; cheaper models implement and review. The plan picks the model per task, and execution enforces it through the project agents `kit:implementer-sonnet`, `kit:implementer-haiku` and `kit:reviewer-sonnet` (`.claude/agents/`), whose frontmatter sets the model, the reasoning effort (`low` for Haiku, `medium` for Sonnet) and a short tool list, even when the parent session is Opus.

- **Tag every plan task** with a `Model: sonnet` or `Model: haiku` line. Untagged means Sonnet.
- **Haiku** only when all hold: the plan gives the exact code or text, the task touches at most 2 files, and it has no SQL, no new logic and no debugging. Examples: doc and README edits, YAML config entries, renames, a test whose body the plan spells out.
- **Sonnet** for everything else: branching logic, DuckDB SQL, changes across modules, fixing a failing test.
- **Escalate, don't retry.** A Haiku task that fails review or tests twice goes to Sonnet.
- **Never pass `model` when dispatching a project agent.** The Agent tool's `model` overrides the frontmatter: on 2026-10-16 an `kit:implementer-sonnet` fix wave ran on Opus that way. Reviews go to `kit:reviewer-sonnet`, never to `general-purpose`, which inherits the parent's model (Opus) and all its tools.

## Subagent cost

Every subagent starts cold: its own system prompt and tool definitions, then CLAUDE.md, `docs/code-conventions.md` and file discovery, before any work. Its context is separate from the main window, but all of its tokens count toward usage. So dispatch fewer, larger units of work:

- **Batch Haiku tasks:** 3–5 consecutive `Model: haiku` tasks go to one `kit:implementer-haiku` call. Sonnet tasks go one per call, or a small batch when they touch the same files.
- **One review per batch, not per task.** One `kit:reviewer-sonnet` checks the batch's diff against its plan sections (spec compliance and code quality in one pass). A batch is the tasks dispatched since the last review, up to 3 Sonnet tasks or one Haiku batch. A re-review checks only the fix diff. This overrides the separate spec and code reviewers per task in `superpowers:subagent-driven-development`.
- **Skip review** for Haiku batches that only edit docs or config: the tests plus the owner's look at the diff are enough.
- **A final whole-branch review** runs on Opus only when the plan asks for one.
- **Keep agent tool lists short.** A new agent sets `tools:` in its frontmatter; inheriting all tools loads every MCP connector's definitions into each subagent.

## Prompt cache

Cached input costs about a tenth of fresh input, so a warm session is cheap per turn. These break the cache: switching model, editing CLAUDE.md or `.claude/agents/` mid-session, enabling or disabling MCP servers or tools, and `/compact`. Make such changes between sessions. `/clear` also discards the cache: clear when the context is large (see Checkpoints), not by reflex.

## Standing rules

1. **Keep always-loaded context small.** CLAUDE.md points to the spec, it doesn't `@`-import it. Never `@` the plan file. Put new workflow-specific rules in a skill or a `docs/` file, not CLAUDE.md.
2. **Split big plans by task.** If a plan section exceeds ~150 lines, split it into `plans/NN-task.md` so a session loads only its own.
3. **Keep tool output short.** `pytest -q` is already set. Use a single file or `-k` while iterating and the full suite once at the end. Never print the cache or API payloads whole. Use DuckDB queries with `LIMIT`. Pipe logs through `head`, `tail` or `grep`.
4. **Search inline first.** In a repo this size, `grep -rn X src | head` costs a few hundred tokens; a search subagent costs thousands to start. Delegate only sweeps across many directories or naming conventions where you want just the conclusion.
5. **Hand off by file, not `/compact`.** At the checkpoint threshold or after an unrelated detour, write decisions and the next step to the plan or spec, `/clear`, then continue from that file.
6. **Constrain output.** For mechanical edits: "diff only, no explanation, don't touch surrounding code."

## Checkpoints

- Run `/context` at the start of a new kind of task. If CLAUDE.md plus imports exceeds ~3k tokens, trim it.
- Hand off by file and `/clear` when the conversation passes ~80k tokens, whatever the turn count. The kit's `context-warn` hook fires once per 80k step: on Stop it tells the owner; on the next prompt it tells Claude to write the handoff into the plan or spec and end its reply with `Handoff: <file>` and `After /clear, paste: continue from <file>, next: <step>`. Claude cannot `/clear` itself; the owner pastes that line after `/clear`. In plan execution the orchestrator hands off between batches: the plan file records which tasks are done.
- Once per plan phase, note `/cost` (or `/usage`) at the end. Before changing these rules, compare a phase run both ways rather than guessing.
- Planned checks over session transcripts, with a 2026-10-16 baseline: `docs/superpowers/specs/2026-10-16-token-usage-roadmap.md`.

## Benchmarks

`kit bench` reads the session transcripts in `~/.claude/projects/` (read-only, counts only) and prints benchmarks B1–B13 with their targets (commands in `docs/command.md`, "Token benchmarks"). Before and after a rule change, run it with `--split <the commit's UTC time>`, and add `--control <repo>` as a control: investment keeps its own rules, so a change that shows in both repos is not this repo's doing.

| # | Benchmark | Rule it checks |
|---|---|---|
| B1–B3 | Peak main-window context: median, share over 80k and over 120k | Checkpoints (hand off by file) |
| B4 | Cache read ÷ output per session | History re-sent over many small turns |
| B5 | Cache breaks per session (a later call whose cache write is over half its prompt) | Prompt cache |
| B6 | Tool results over 20k characters per transcript | Standing rule 3 |
| B7 | First-call cache write of an implementer: its startup cost | Short agent tool lists |
| B8 | Reviewers per implementer | One review per batch |
| B9 | Opus subagents other than a final review | Model routing, no `model` override |
| B10 | Tasks per Haiku implementer (from "Tasks 3-5" in the description) | Batch Haiku tasks |
| B11 | Search subagents per session | Standing rule 4 |
| B12 | Cost per implemented task in plan runs (4+ implementers) | All of the above, end to end |
| B13 | Cost per owner prompt | Everything, across all kinds of session |

Cost is a proxy in fresh-input tokens: cache write ×1.25, cache read ×0.1, output ×5. Subagent transcripts record almost no output tokens, so subagent cost is a little low. Read B12 and B13 as trends, not prices. A single plan run moves them a lot, so compare at least two runs per side.

## Not worth doing here

`repomix` (small repo). MCP pruning in the main session: the claude.ai connectors load as deferred tools (names only until used); subagents avoid them through their `tools:` list.
