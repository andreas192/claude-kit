# kit insights: a weekly report on loop cost, session cost and what to change

## Why

The owner runs the feature loop on `dividend-growth` and `investment` and works in them by hand. `kit bench` compares kit versions, but someone has to run it, and it says nothing about the loop. Each loop stage is a `claude -p` session, but its cost, tokens and outcome are not recorded, so there is no way to tell which stage costs the most, how often items park or loop in `build`, or whether a new kit version made the loop cheaper. The owner wants a command that runs on its own every week, compares this week with earlier weeks and each kit version with the one before, and says in plain words what to change in the loop, in token use or in the process.

## Goals

- The loop driver records each stage it runs: cost, tokens, duration, turns, outcome, model, kit version, item and session id. It also records each run's stop reason.
- `kit insights run` builds one report for every kit repo under `--base`. For each repo it shows week by week and kit version by version:
  - loop cost per stage
  - items shipped and parked
  - build iterations
  - errors and usage stops
  - the interactive-session benchmarks
- The report ends with findings. Each finding is a rule over the numbers, shows the numbers that triggered it and suggests one change.
- An optional advisor step (on by default in the scheduled run) gives one Sonnet session the numbers-only report and read access to the kit's own prompts, agents and token rules. It appends up to 8 concrete suggested changes.
- `kit insights install|uninstall` sets up a weekly launchd agent (Monday 09:00) that runs it and shows a macOS notification with the report path.

## Non-goals

- Changing the kit, the roadmap or any repo based on the findings. The report suggests; the owner decides.
- Dollar billing accuracy. Loop cost uses `total_cost_usd` from the `claude -p` result. Interactive cost uses the existing fresh-token cost proxy. The two are never added together.
- Charts or HTML. The report is markdown.

## Anti-goals

- Message text in the report. Like `bench`, it carries counts and ratios only. The advisor sees only that report and the kit's own files, never transcripts.
- Writing into the repos. Reports go to `~/.claude/kit/insights/`, which `KIT_HOME` already owns.
- A finding on too little data. Interactive rules need `MIN_SESSIONS` sessions in the week. Loop rules need at least one shipped or parked item.

## Decided

### Stage ledger

- `parse_stream` also reads the `result` event's `total_cost_usd`, `usage` (input, cache creation, cache read, output), `duration_ms`, `num_turns` and `session_id` into a `StageCost`. A missing or malformed field gives `None` (no cost) rather than an error.
- After each stage (and the probe), the driver appends one JSON line to `<runtime>/stages.jsonl`. Each line carries a `time`, `kind: "stage"`, the stage fields and the running kit version. The driver also appends `kind: "stop"` with the stop reason when a run ends.
- The ledger is append-only. Insights reads it and skips lines it cannot parse.

### Weeks and versions

- Weeks are ISO weeks in UTC (Monday 00:00 to Monday 00:00). A report covers the last `--weeks` (default 6) complete weeks before today. The current, unfinished week is left out.
- Version windows reuse `bench`'s windows from `.claude/kit.json`, with apply-PR merge times.
- Interactive sessions are the repo's transcripts minus the session ids found in its ledger. From now on, loop sessions no longer skew the interactive numbers.

### Report (`~/.claude/kit/insights/<YYYY>-W<ww>.md`)

Per repo:

1. **Loop by week**: runs, stages, shipped (pr ok), parked, build iterations per shipped item, errors, usage stops, cost $ per stage (probe, spec, plan, build, pr), total $, $ per shipped item, and the median peak context (k) of the stages.
2. **Loop by version**: the same columns, grouped by the `kit_version` recorded on each line.
3. **Sessions by week**: `bench`'s table (`report_lines`) with weeks as columns, including week-over-week deltas.
4. **Findings.**

Then the advisor's `## Suggested changes`, if it ran.

### Findings (rules with named thresholds)

| id | rule | suggestion |
|---|---|---|
| L1 | spec + plan share of loop $ > 50% | try `plan` on Sonnet, or shorten the spec prompt |
| L2 | build iterations per shipped item > 3 | plans are too big; ask the plan stage for smaller tasks |
| L3 | parked share of finished items > 30% | open roadmap items need more detail before they reach `open` |
| L4 | stage errors in the week > 0 | read `loop.log`; permission denials point to `.claude/loop-settings.json` |
| L5 | usage stops in the week >= 2 | raise `loop.interval_hours` |
| L6 | $ per shipped item up > 25% on the previous week | regression; the finding names the kit version applied in that week, if any |
| L7 | median stage peak context > 80k | the stage reads too much; trim the read-first list or split the stage |
| S1 | B1 > 80 | context runs long; use `/clear` between tasks |
| S2 | B5 > 2 | cache breaks; avoid changing settings, model or tools mid-session |
| S3 | B8 > 0.5 | too many reviewers per implementer; batch reviews |
| S4 | B9 > 0 | Opus subagents outside a final review |
| S5 | F1 > 1 | permission denials; run `/fewer-permission-prompts` |
| S6 | B13 up > 25% on the previous week | session cost regression |

### Advisor

`claude -p` on `sonnet` with medium effort, cwd the kit repo, `--permission-mode dontAsk` and a settings file that allows only `Read`, `Grep` and `Glob`. The prompt gives the report and asks for up to 8 bullets. Each bullet names a file in the kit and a change, cites a number from the report, and says which finding it addresses. The advisor's own cost goes in the report. `--no-advise` skips it, and a failed advisor writes one line and the report stays.

### Schedule

`com.kit.insights.plist` in `~/Library/LaunchAgents`, `StartCalendarInterval` Monday 09:00. It runs `uv run --project <kit repo> kit insights run --base <base>` (the kit checkout, not a snapshot: insights is about the kit, so it runs the newest code). It logs to `~/.claude/kit/insights/launchd.log`.

## Left to the builder

- Module layout. The intended layout is `kit/insights/` with `ledger.py`, `weeks.py`, `loopstats.py`, `findings.py`, `report.py`, `advise.py`, and wiring in `insights_cmd.py`.
- The column formatting.

## Calls made for the owner

- Weekly cadence plus version columns in the same report. Rejected: a run per kit release (releases are rare, so the report would almost never run).
- Loop cost from `total_cost_usd`. Rejected: rebuilding it from transcripts (the CLI already computes it, and transcripts of `-p` runs may be pruned).
- Reports in `~/.claude/kit/insights/`. Rejected: committing them into each repo (noise in the repo, and the report spans repos).
- An LLM advisor on top of fixed rules. Rejected: rules only (they cannot point at a specific prompt line), and an advisor only (its numbers cannot be checked).
