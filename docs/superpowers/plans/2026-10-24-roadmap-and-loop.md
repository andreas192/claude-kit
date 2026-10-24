# kit v0.2.0: standard roadmap and feature loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task carries a `Model:` tag; route it to the matching implementer agent and never pass `model` when dispatching one.

**Goal:** One roadmap format (`docs/roadmap.md`) that `kit roadmap` validates and reports on, and dividend-growth's feature loop moved into the kit as `kit loop`, picking deterministically, running on weekdays only and parking every decision that is the owner's.

**Architecture:** `kit/roadmap.py` parses and validates the file. `kit/loop/` holds the loop: pure modules (`pick`, `prs`, `stream`, `state`, `settings`, `schedule`, `handover`) and the ported stage machine (`driver.py`). `kit/loop_cmd.py` is wiring for the `kit loop` subcommands. From v0.2.0 on, a version snapshot also holds the tag's `src/kit`, and launchd runs `python -m kit.cli loop run <repo>` from it with `PYTHONPATH`, so the loop never runs code from the kit's working tree.

**Tech Stack:** Python 3.12, standard library only at runtime, `pytest`; `git`, `gh`, `claude`, `launchctl` and `osascript` as subprocesses behind injected seams.

**Spec:** `docs/superpowers/specs/2026-10-24-roadmap-and-loop-design.md`. Port source (read-only): `../dividend-growth/scripts/feature_loop.py`, `../dividend-growth/scripts/loop_prompts/*.md`, `../dividend-growth/tests/test_feature_loop.py`.

## Decisions this plan adds to the spec

- **Driver handover.** `kit loop run` reads `.claude/kit.json` on `origin/<base_branch>`. If its last applied version is newer than the running `kit.__version__` and `~/.claude/kit/<v>/src/kit` exists, it runs `sys.executable -m kit.cli loop run <repo> --no-handover` with `PYTHONPATH=<snapshot>/src` and returns that exit code.
- **Snapshot.** `snapshot()` also exports `<tag>:src/kit` to `<snapshot>/src/kit`, but only when the tag contains `src/kit/loop/`, so a v0.1.0 snapshot made today keeps its digest.
- **Runtime directory.** `~/.claude/kit/loop/<repo-name>/` holds `lock`, `loop.log`, `launchd.log`, `state.json`, `settings.json`, `note.md`, `note-body.md` and `pr-body.md`. The PR stage writes its body there, and the generated settings allow `Write` to that directory only.
- **Base loop permissions** ship as `src/kit/loop/base-settings.json`, inside the package and therefore inside the snapshot. They also allow `gh pr edit` and `gh pr ready`, which a resumed item needs to promote its draft PR.
- **Resumed drafts.** The PR stage counts as done only when the branch has an open PR that is not a draft. A resumed item's PR stage edits and readies the existing draft.
- **Roadmap fields** must start on the line right after the `###` heading. The first non-field line, including a blank one, ends them.
- **`kit roadmap` without `gh`.** It still validates and counts. The next pick and the parked PRs print as `unknown (gh: <reason>)`.

## Global Constraints

- No `pip install`, `uv tool install`, `uvx` or `uv pip install --system`. The kit runs as `uv run --project <kit> kit ...` from its own `.venv`; the loop runs as `uv run --no-project python -m kit.cli ...` from a snapshot. No Homebrew, shell-profile or `podman machine` changes.
- `apply` writes only inside the target repo and inside `~/.claude/kit/`. It never merges a PR. `bench` writes only `.claude/kit-bench/`.
- `kit loop install` and `kit loop uninstall` may also write `~/Library/LaunchAgents/com.kit.loop.<repo-name>.plist` and call `launchctl` for that label only.
- The loop's runtime files live in `~/.claude/kit/loop/<repo-name>/`, never in the repo's tracked tree.
- Standard library only at runtime. The loop driver imports only `kit.*` and the standard library.
- Tests run offline with fixtures built in code. No real `claude`, `gh`, `launchctl` or `osascript`; `git` runs on temp repos. Never read the real `~/.claude/projects/` or `~/Library/LaunchAgents/` in tests.
- Follow `docs/code-conventions.md`. `cli.py`, `apply.py`, `bench/run.py` and `loop_cmd.py` are wiring. UNIT tests sit beside each module; PIPELINE tests go only in `tests/test_cli_pipeline.py`.
- Roadmap path `docs/roadmap.md`. Statuses exactly `open`, `owner`, `blocked`, `active`, `done`, `dropped`. Fields exactly `Status`, `Blocked by`, `Depends on`, `Spec`, `Plan`, `PR`. Key cut `KEY_MAX = 50`.
- Loop names: branch prefix `loop/`, status file `.loop/status.json`, worktree `.claude/worktrees/feature-loop`, launchd label `com.kit.loop.<repo-name>`, notification title `kit loop: <repo-name>`, `DEFAULT_INTERVAL_HOURS = 5`.
- Stage models unchanged from dividend-growth: probe haiku (no effort), spec opus high, plan opus medium, build sonnet medium, pr sonnet medium. There is no pick stage.
- Every loop commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The last line of every loop PR body is `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Never write to `../investment` or `../capital-trading`; reading `../dividend-growth` to port and hash files is read-only.

## Review Focus

1. **A parked item that the owner resumed.** Its draft PR already exists, so `gh pr create` would fail. The PR stage must edit and ready the draft, and the driver must treat "only a draft is open" as not done (test in task 7).
2. **In-flight dividend-growth branches.** Titles taken verbatim from the old roadmap's first cells must give the existing `loop/*` names, including the two keys cut at 50 characters (test in task 1).
3. **`kit apply` after the owner adds a `loop` section.** `write_kitfile` and `apply` must keep the section; today both rebuild `KitFile` from `test_command` and `applies` only (tests in task 3).
4. **The weekend boundary.** A stage that ends after Saturday 00:00 is followed by no stage, and a run that starts on a Sunday makes no `claude` call at all, the probe included (test in task 8).
5. **Relative forbidden paths.** `../investment` must resolve against the repo, not the worktree two levels down, or the deny rules point at the wrong folder (test in task 4).

---

### Task 1: Roadmap parser and validator

Model: sonnet

**Files:**
- Create: `src/kit/roadmap.py`
- Test: `tests/test_roadmap.py`

**Interfaces:**
- Produces: `ROADMAP_PATH = Path("docs") / "roadmap.md"`; `STATUSES`; `KEY_MAX = 50`; `item_key(title: str) -> str` (dividend-growth's rule: lowercase, runs of `[^a-z0-9]` to `-`, strip `-`, and if longer than 50, `key[:51].rsplit("-", 1)[0]`); `@dataclass(frozen=True) Item(title: str, key: str, section: str, status: str, blocked_by: str, depends_on: tuple[str, ...], spec: str, plan: str, pr: str, line: int)`; `@dataclass(frozen=True) Roadmap(items: tuple[Item, ...])`, with method `by_title(title) -> Item`; `@dataclass(frozen=True) Problem(line: int, message: str)`; `class RoadmapError(KitError)` with `.problems: tuple[Problem, ...]`, whose `str()` is the problems as `docs/roadmap.md:<line>: <message>`, one per line; `parse_roadmap(text: str) -> Roadmap` (collects all problems, then raises once); `read_roadmap(repo: Path) -> Roadmap` (`KitError("<repo>/docs/roadmap.md not found")` when missing).

- [ ] **Step 1: Write the failing tests**

```python
GOOD = """# Roadmap

## Features

### Two-stage dividend discount model
- Status: open

Body text.

### Valuation against the company's own history
- Status: open
- Depends on: Two-stage dividend discount model

### Host port for the UI
- Status: owner
- Blocked by: whether to recreate the cluster

## Known data bugs

### Dividend pay dates and calendar
- Status: done
- Spec: docs/superpowers/specs/2026-10-18-dividend-pay-dates-and-calendar-design.md
"""

def test_parse_keeps_file_order_sections_and_fields():
    r = parse_roadmap(GOOD)
    assert [i.status for i in r.items] == ["open", "open", "owner", "done"]
    v = r.items[1]
    assert (v.section, v.depends_on, v.key) == ("Features", ("Two-stage dividend discount model",), "valuation-against-the-company-s-own-history")
    assert r.items[2].blocked_by == "whether to recreate the cluster" and r.items[3].section == "Known data bugs"

@pytest.mark.parametrize("title, branch_key", [
    ("Automatic classification of one-off dividend schedule shifts (a short year whose gaps between payments are all normal), so Data fixes needs fewer manual settlements", "automatic-classification-of-one-off-dividend"),
    ("Regime or beta as a scoring input (option 3 of 2026-10-14)", "regime-or-beta-as-a-scoring-input-option-3-of-2026"),
    ("Holdings and income projection (yield on cost, concentration, forward income)", "holdings-and-income-projection-yield-on-cost"),
])
def test_item_key_matches_the_existing_loop_branches(title, branch_key):
    assert item_key(title) == branch_key

def test_crlf_and_trailing_spaces_are_tolerated():
    assert parse_roadmap(GOOD.replace("\n", "\r\n").replace("Status: open", "Status: open  ")).items[0].status == "open"

@pytest.mark.parametrize("fields, message", [
    ("", "missing Status"),
    ("- Status: later", "unknown Status 'later'"),
    ("- Status: blocked", "Blocked by is required when Status is blocked"),
    ("- Status: open\n- Blocked by: x", "Blocked by is only for owner or blocked"),
    ("- Status: open\n- Owner: me", "unknown field 'Owner'"),
    ("- Status: open\n- Depends on: Nowhere", "Depends on 'Nowhere' is not an item"),
])
def test_each_problem_names_its_line(fields, message):
    with pytest.raises(RoadmapError) as e:
        parse_roadmap(f"# Roadmap\n\n### A\n{fields}\n")
    assert e.value.problems[0].line == 3 and message in e.value.problems[0].message

def test_duplicate_keys_are_one_problem_per_repeat():
    with pytest.raises(RoadmapError, match="duplicate key 'a-b'"):
        parse_roadmap("### A b\n- Status: open\n\n### A-b\n- Status: open\n")

def test_all_problems_are_reported_at_once():
    with pytest.raises(RoadmapError) as e:
        parse_roadmap("### A\n\n### B\n- Status: x\n")
    assert len(e.value.problems) == 2
```

- [ ] **Step 2: Run** `uv run pytest tests/test_roadmap.py`. Expect FAIL (module missing).
- [ ] **Step 3: Implement** `src/kit/roadmap.py` with the signatures above. Use a field-line regex `^- (Status|Blocked by|Depends on|Spec|Plan|PR): (.*)$`; any other `^- [A-Za-z ]+: ` line directly under the heading is an unknown field. Split `Depends on` on commas and strip each title.
- [ ] **Step 4: Run** `uv run pytest tests/test_roadmap.py`. Expect PASS.
- [ ] **Step 5: Commit** `git add src/kit/roadmap.py tests/test_roadmap.py && git commit -m "feat(roadmap): parse and validate docs/roadmap.md"`

### Task 2: Loop PRs and the deterministic pick

Model: sonnet

**Files:**
- Create: `src/kit/loop/__init__.py` (empty), `src/kit/loop/prs.py`, `src/kit/loop/pick.py`
- Test: `tests/test_loop_prs.py`, `tests/test_loop_pick.py`

**Interfaces:**
- Consumes: `Roadmap`, `Item` (task 1).
- Produces, in `prs.py`:
  - `PR_FIELDS = "number,headRefName,state,createdAt,url,title,isDraft,body"`;
  - `@dataclass(frozen=True) Pr(number: int, head: str, state: str, created: str, url: str, title: str = "", is_draft: bool = False, body: str = "")`;
  - `loop_prs(gh_json: str) -> list[Pr]`: `loop/` heads only, sorted by `created`;
  - `park_body(reason: str, spec: str, plan: str, questions: list[str]) -> str`: `Parked: <reason>`, then the spec and plan lines when given, then `## Questions for the owner` with one `- ` bullet per question when there are any, then the attribution line;
  - `@dataclass(frozen=True) ParkNote(reason: str, questions: tuple[str, ...])` and `parse_park_body(body: str) -> ParkNote`, the inverse of `park_body`.
- Produces, in `pick.py`:
  - `@dataclass(frozen=True) Skip(item: Item, reason: str)`;
  - `@dataclass(frozen=True) Pick(item: Item | None, skipped: tuple[Skip, ...])`;
  - `pick(roadmap: Roadmap, branches: list[str], prs: list[Pr]) -> Pick`: considers `open` items only, in file order. A taken item gives the reason `taken by <newest PR url for loop/<key>>`, or `taken by branch loop/<key>` when there is no PR; a dependency not done gives `depends on <title> (<status>)`. The first open item without a reason is the pick; reasons are collected for every open item;
  - `none_note(roadmap: Roadmap, prs: list[Pr]) -> str`: Markdown with `## Waiting on the owner` (the owner items as `- <title>: <blocked_by>`), `## Blocked` (the same for blocked items) and `## Parked loop PRs` (each draft as `- <url>: <reason>`), and a section is left out when it is empty.

- [ ] **Step 1: Write the failing tests**

```python
def test_pick_is_the_first_open_item_not_taken_and_unblocked(roadmap):  # roadmap: GOOD of task 1 as a fixture
    p = pick(roadmap, branches=[], prs=[])
    assert p.item.title == "Two-stage dividend discount model"
    assert [(s.item.title, s.reason) for s in p.skipped] == [("Valuation against the company's own history", "depends on Two-stage dividend discount model (open)")]

def test_a_pr_in_any_state_or_a_bare_branch_takes_an_item(roadmap):
    pr = Pr(7, "loop/two-stage-dividend-discount-model", "CLOSED", "2026-10-20", "https://x/pull/7")
    assert pick(roadmap, [], [pr]).skipped[0].reason == "taken by https://x/pull/7"
    assert pick(roadmap, ["loop/two-stage-dividend-discount-model"], []).skipped[0].reason == "taken by branch loop/two-stage-dividend-discount-model"

def test_owner_blocked_and_active_items_are_never_picked():
    r = parse_roadmap("### A\n- Status: owner\n- Blocked by: me\n\n### B\n- Status: active\n")
    assert pick(r, [], []) == Pick(None, ())

def test_park_body_round_trips_with_questions():
    body = park_body("owner questions", "s.md", "p.md", ["Include REITs? Recommended: no"])
    assert parse_park_body(body) == ParkNote("owner questions", ("Include REITs? Recommended: no",))
    assert body.rstrip().endswith("🤖 Generated with [Claude Code](https://claude.com/claude-code)")

def test_none_note_lists_owner_items_and_parked_drafts(roadmap):
    draft = Pr(9, "loop/x", "OPEN", "2026-10-21", "https://x/pull/9", is_draft=True, body=park_body("tests red", "", "", []))
    note = none_note(roadmap, [draft])
    assert "- Host port for the UI: whether to recreate the cluster" in note and "- https://x/pull/9: tests red" in note
    assert "## Blocked" not in note
```

Also carry over dividend-growth's `test_loop_prs_keeps_loop_heads_sorted`, reading `isDraft` and `body` now.

- [ ] **Step 2: Run** `uv run pytest tests/test_loop_prs.py tests/test_loop_pick.py`. Expect FAIL.
- [ ] **Step 3: Implement** both modules.
- [ ] **Step 4: Run** them again. Expect PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(loop): deterministic pick over the roadmap and loop PRs"` (add the four files).

### Task 3: `loop` section in `.claude/kit.json`

Model: haiku

**Files:**
- Modify: `src/kit/kitfile.py`, `src/kit/apply.py:70-72` (the `write_kitfile(... KitFile(resolved.test_command, kit.applies))` line)
- Test: `tests/test_kitfile.py`, `tests/test_cli_pipeline.py` (one assertion added to the existing apply happy path)

**Interfaces:**
- Produces: `DEFAULT_INTERVAL_HOURS = 5`; `@dataclass(frozen=True) LoopConfig(base_branch: str, forbidden_paths: tuple[str, ...] = (), read_first: tuple[str, ...] = (), pr_checklist: tuple[str, ...] = (), interval_hours: int = DEFAULT_INTERVAL_HOURS)`; `KitFile(test_command: str, applies: tuple[Apply, ...], loop: LoopConfig | None = None)`. `parse_kitfile` reads the optional `loop` object. It raises `KitError` (`"<path>: invalid kit.json: ..."`) for an unknown key in `loop`, a missing or empty `base_branch`, a list that is not of strings, or `interval_hours` outside 1..24. `write_kitfile` writes `loop` only when it is set (tuples become lists, every key included). `with_apply` keeps `loop`.

- [ ] **Step 1: Write the failing tests**

```python
LOOP = {"base_branch": "develop", "forbidden_paths": ["../investment"], "interval_hours": 5}

def test_loop_section_round_trips(tmp_path):
    kit = parse_kitfile(json.dumps({"test_command": "t", "applies": [], "loop": LOOP}))
    assert kit.loop == LoopConfig("develop", ("../investment",))
    write_kitfile(tmp_path, with_apply(kit, Apply("v0.2.0", "c", "2026-10-24T00:00:00Z")))
    assert read_kitfile(tmp_path).loop == kit.loop

@pytest.mark.parametrize("loop", [{"base_branch": ""}, {"base_branch": "d", "schedule": 1}, {"base_branch": "d", "interval_hours": 0}, {"base_branch": "d", "read_first": "x"}])
def test_bad_loop_section_is_a_kit_error(tmp_path, loop):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/kit.json").write_text(json.dumps({"test_command": "t", "applies": [], "loop": loop}))
    with pytest.raises(KitError, match="invalid kit.json"):
        read_kitfile(tmp_path)
```

In `tests/test_cli_pipeline.py`, extend `test_apply_a_newer_version_replaces_the_marketplace_entry`: write a `loop` section into the target's `kit.json` and commit it between the two applies, then assert that `read_kitfile(target).loop.base_branch == "develop"` after the second apply.

- [ ] **Step 2: Run** `uv run pytest tests/test_kitfile.py tests/test_cli_pipeline.py -k "loop or newer"`. Expect FAIL.
- [ ] **Step 3: Implement** the changes in `kitfile.py`, and pass `loop=kit.loop` in `apply.py`.
- [ ] **Step 4: Run** again. Expect PASS.
- [ ] **Step 5: Commit** `git commit -am "feat(kitfile): loop section, kept across applies"`

### Task 4: Generated loop permissions

Model: haiku

**Files:**
- Create: `src/kit/loop/base-settings.json`, `src/kit/loop/settings.py`
- Test: `tests/test_loop_settings.py`

**Interfaces:**
- Produces: `base_settings() -> dict`, which reads the JSON beside the module; `loop_settings(base: dict, extra: dict, repo: Path, forbidden: tuple[str, ...], test_command: str, runtime: Path) -> dict`. It returns `{"permissions": {"allow": [...], "deny": [...]}}`:
  - `allow` is the base allow list, then the extra one, then `Bash(<test_command>*)` and `Write(<runtime>/**)`;
  - `deny` is the base deny list, then the extra one, then `Edit(<abs>/**)` and `Write(<abs>/**)` for each forbidden path, where `abs = (repo / path).resolve()`;
  - each list is de-duplicated in its first-seen order. Other top-level keys of `extra` are not copied.

`base-settings.json`, exactly:
- allow: `Read`, `Glob`, `Grep`, `Edit(./**)`, `Write(./**)`, `Agent`, `Skill`, `TodoWrite`, and `Bash(<x> *)` for `git status`, `git diff`, `git log`, `git show`, `git add`, `git commit`, `git rm`, `git rev-parse`, `gh pr create`, `gh pr view`, `gh pr list`, `gh pr edit`, `gh pr ready`, `ls`, `grep`, `head`, `tail`, `wc`;
- deny: `Bash(<x>*)` for `git push`, `git checkout`, `git switch`, `git worktree`, `gh pr merge`, `gh pr close`, `gh api`, `gh repo`, `pip `, `uv pip `, `uv tool `, `brew `, `podman `, `docker `.

- [ ] **Step 1: Write the failing tests**

```python
def test_forbidden_paths_resolve_against_the_repo_not_the_worktree(tmp_path):
    repo = tmp_path / "dividend-growth"; repo.mkdir()
    s = loop_settings(base_settings(), {}, repo, ("../investment",), "uv run pytest -q", tmp_path / "rt")
    inv = (tmp_path / "investment").resolve()
    assert f"Edit({inv}/**)" in s["permissions"]["deny"] and f"Write({inv}/**)" in s["permissions"]["deny"]

def test_repo_extras_are_unioned_without_duplicates(tmp_path):
    extra = {"permissions": {"allow": ["Read", "Bash(uv run dgi *)"], "deny": ["Bash(gh api*)", "Bash(kubectl *)"]}, "env": {"X": "1"}}
    s = loop_settings(base_settings(), extra, tmp_path, (), "uv run pytest -q", tmp_path / "rt")
    allow, deny = s["permissions"]["allow"], s["permissions"]["deny"]
    assert allow.count("Read") == 1 and "Bash(uv run dgi *)" in allow and "Bash(uv run pytest -q*)" in allow
    assert f"Write({tmp_path / 'rt'}/**)" in allow and deny.count("Bash(gh api*)") == 1 and "env" not in s

def test_base_denies_pushes_merges_and_installs():
    deny = base_settings()["permissions"]["deny"]
    assert {"Bash(git push*)", "Bash(gh pr merge*)", "Bash(pip *)", "Bash(uv tool *)"} <= set(deny)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_loop_settings.py`. Expect FAIL.
- [ ] **Step 3: Implement** the two files, and include the JSON in the wheel (hatch already packages all of `src/kit`; check that `base_settings()` works from an installed `.venv`).
- [ ] **Step 4: Run** again. Expect PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(loop): generated permissions for loop sessions"` (add the files).

### Task 5: Weekday schedule and launchd plist

Model: haiku

**Files:**
- Create: `src/kit/loop/schedule.py`
- Test: `tests/test_loop_schedule.py`

**Interfaces:**
- Produces:
  - `may_start(now: datetime) -> bool`: Monday to Friday, local time;
  - `run_hours(interval_hours: int) -> list[int]`: `list(range(0, 24, interval_hours))`;
  - `loop_label(repo_name: str) -> str`: `com.kit.loop.<repo_name>`;
  - `plist_xml(label: str, program: list[str], env: dict[str, str], workdir: Path, log: Path, hours: list[int]) -> str`: `StartCalendarInterval` is an array with one `{Weekday, Hour, Minute: 0}` dict per weekday 1..5 per hour, `RunAtLoad` false, `StandardOutPath` and `StandardErrorPath` set to `log`, and no `StartInterval`. Escape values with `xml.sax.saxutils.escape`;
  - `other_loop_agents(agents_dir: Path, repo: Path, own_label: str) -> list[Path]`: every `*.plist` in `agents_dir` whose text contains `str(repo)` and whose name is not `<own_label>.plist`, sorted.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("day, ok", [("2026-10-23", True), ("2026-10-24", False), ("2026-10-25", False), ("2026-10-26", True)])
def test_may_start_on_weekdays_only(day, ok):
    assert may_start(datetime.fromisoformat(f"{day}T10:00")) is ok

def test_plist_has_weekday_hours_and_no_interval(tmp_path):
    xml = plist_xml("com.kit.loop.dg", ["uv", "run"], {"PYTHONPATH": "/s/src"}, tmp_path, tmp_path / "l.log", run_hours(5))
    d = plistlib.loads(xml.encode())
    assert len(d["StartCalendarInterval"]) == 25 and {e["Weekday"] for e in d["StartCalendarInterval"]} == {1, 2, 3, 4, 5}
    assert {e["Hour"] for e in d["StartCalendarInterval"]} == {0, 5, 10, 15, 20} and "StartInterval" not in d
    assert d["EnvironmentVariables"]["PYTHONPATH"] == "/s/src" and d["RunAtLoad"] is False

def test_other_loop_agents_finds_the_old_dgi_agent(tmp_path):
    (tmp_path / "com.dgi.feature-loop.plist").write_text("<string>/p/dividend-growth/data/loop/bin/feature_loop.py</string>")
    (tmp_path / "com.kit.loop.dividend-growth.plist").write_text("/p/dividend-growth")
    assert other_loop_agents(tmp_path, Path("/p/dividend-growth"), "com.kit.loop.dividend-growth") == [tmp_path / "com.dgi.feature-loop.plist"]
```

- [ ] **Step 2: Run** `uv run pytest tests/test_loop_schedule.py`. Expect FAIL.
- [ ] **Step 3: Implement** `schedule.py`.
- [ ] **Step 4: Run** again. Expect PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(loop): weekday schedule and launchd plist"` (add the files).

### Task 6: Port the stage machine, with the pick in code

Model: sonnet

**Files:**
- Create: `src/kit/loop/stream.py`, `src/kit/loop/state.py`, `src/kit/loop/driver.py`, `src/kit/loop/prompts/{probe,spec,plan,build,pr}.md`
- Test: `tests/test_loop_stream.py`, `tests/test_loop_state.py`, `tests/test_loop_driver.py`

**Interfaces:**
- Consumes: `parse_roadmap`, `item_key` (task 1); `Pr`, `loop_prs`, `PR_FIELDS`, `park_body`, `pick`, `none_note` (task 2); `LoopConfig` (task 3).
- Produces:
  - `stream.py`: `Usage`, `StageResult`, `parse_stream`, `over_limit` (`LIMIT = 0.8`), `stream_lines`, `STAGE_MODELS`, `claude_command(stage, text, settings: Path) -> list[str]`, all as in dividend-growth. `STAGE_MODELS` has no `pick` entry.
  - `state.py`: `STAGES = ("spec", "plan", "build", "pr")`, `Status`, `read_status`, `write_status`, `resume_stage`, `next_stage`, `new_status(title, today)`, `is_live`, `unfinished`, `has_calls_section`, all as in dividend-growth. `item_key` is the one from `kit.roadmap`.
  - `driver.py`:
    - `@dataclass Env(claude: Callable[[str, str], list[str]], sh: Callable[[list[str]], str], notify: Callable[[str], None], log: Callable[[str], None], worktree: Path, runtime: Path, today: str, now: Callable[[], datetime], config: LoopConfig, test_command: str, repo_name: str, weekend_ok: bool = False)`;
    - `render(stage: str, env: Env, **fields: str) -> str`;
    - `acquire_lock(path) -> IO | None`;
    - `run(env: Env) -> str`; `pick_only(env: Env) -> str`; `guarded(env, action) -> int`.

Port `feature_loop.py` and its tests, changing only the following:
- `origin/develop` and `--base develop` become `origin/<config.base_branch>` and `--base <config.base_branch>`.
- `state.json`, `note.md` and `note-body.md` move to `env.runtime`.
- The notification title becomes `kit loop: <repo_name>`, and its text names `<runtime>/loop.log`.
- **Pick in code.** `_Run.pick` reads `git show origin/<base>:docs/roadmap.md` and parses it. A `RoadmapError` goes to `self.failed("roadmap: <first problem>")`. The `none_key` uses the blob of `docs/roadmap.md`. A `Pick` with no item writes `none_note(...)` to `runtime/note.md` and posts it as today. Otherwise `new_status(pick.item.title, env.today)` and the branch work run as today. The pick stage, `pick.md`, the `pick` outcome in `_LOOP` and the "pick stage chose a taken item" check are removed.
- **Prompts** use `{test_command}`, `{base_branch}`, `{rules}`, `{read_first}` (spec stage), `{pr_checklist}` (PR stage, numbered steps between the test run and `gh pr create`) and `{pr_body}` (`<runtime>/pr-body.md`).
  - `{rules}` is dividend-growth's rules line with `never write <path or path>` built from `forbidden_paths` (left out when there are none).
  - The spec stage's persona is "the domain expert CLAUDE.md describes". The PR body's "the investor view" becomes "the user's view".
  - The PR stage also sets the item's `Status: done`, `Spec`, `Plan` and `PR` in `docs/roadmap.md` after creating the PR, and commits.
  - `_open_draft` uses `park_body(reason, spec, plan, [])`.

Tests: port every test in `../dividend-growth/tests/test_feature_loop.py` except the pick-stage tests (`test_pick_prompt_gets_the_gold_schema_path_and_pr_titles`, `test_pick_of_a_taken_item_is_a_failure`, `test_pick_of_a_remote_branch_is_a_failure`, `test_note_is_read_from_the_fixed_path_and_deleted_before_the_pick`), the settings and install tests (now in tasks 4, 5 and 10) and `test_settings_file_prefers_the_rendered_copy_beside_the_driver`. `FakeEnv.sh` answers `git show origin/develop:docs/roadmap.md` with a roadmap string, and `git rev-parse origin/develop:docs/roadmap.md` with a blob id derived from it. Add these tests:

```python
def test_picks_the_first_open_item_of_the_base_roadmap(tmp_path):
    reason, fake = run_fake(tmp_path, roadmap=ROADMAP_A_OPEN)  # "### Row A\n- Status: open\n"
    assert any(c[:4] == ["git", "checkout", "-B", "loop/row-a"] for c in fake.calls)

def test_invalid_roadmap_is_an_env_failure_naming_the_line(tmp_path):
    reason, fake = run_fake(tmp_path, roadmap="### A\n- Status: soon\n")
    assert reason == "env" and fake.stages == ["probe"]  # two failed picks in a row stop the run
    assert any("roadmap: docs/roadmap.md:2:" in m for m in fake.notices)

def test_prompts_name_the_configured_base_and_forbidden_paths():
    text = render("pr", env_with(LoopConfig("main", ("../a", "../b"))), row="R", key="r", branch="loop/r", spec="s", plan="p")
    assert "--base main" in text and "never write `../a` or `../b`" in text and "{" not in text
```

- [ ] **Step 1: Write the ported and new tests.** Run `uv run pytest tests/test_loop_stream.py tests/test_loop_state.py tests/test_loop_driver.py` and expect FAIL.
- [ ] **Step 2: Implement** the three modules and five prompts.
- [ ] **Step 3: Run** the three test files. Expect PASS. Then run `uv run pytest -q` for the full suite.
- [ ] **Step 4: Commit** `git commit -m "feat(loop): stage machine ported from dividend-growth, pick in code"` (add the files).

### Task 7: The owner's decisions park, and resumed drafts finish

Model: sonnet

**Files:**
- Modify: `src/kit/loop/state.py`, `src/kit/loop/driver.py`, `src/kit/loop/prompts/spec.md`, `src/kit/loop/prompts/pr.md`
- Test: `tests/test_loop_state.py`, `tests/test_loop_driver.py`

**Interfaces:**
- Produces: `QUESTIONS_HEADING = "## Questions for the owner"`; `owner_questions(spec_text: str) -> list[str]`, the `- ` bullets under that heading up to the next `## `, with the bullet marker stripped.

Behaviour:
- **PR-stage gate.** Before the PR stage, a spec with `owner_questions` parks with the reason `owner questions in <spec>`. This check runs before `has_calls_section`.
- **Drafts carry the questions.** `_open_draft` passes `owner_questions(spec text)` to `park_body`.
- **A draft is not done.** The PR stage's ok check asks `gh pr list --head <branch> --state open --json number,isDraft` and needs at least one PR whose `isDraft` is false; otherwise it is `StageResult("error", "pr stage reported ok but no ready PR exists")`.
- **`spec.md`** takes the three piles from the spec, word for word. Owner questions go under `## Questions for the owner`, each with its recommended answer, followed by `LOOP: park owner questions`. Add: "If `{spec}` already exists, the owner answered its questions in it: finish the spec from those answers and leave the questions section empty."
- **`pr.md`.** If an open draft PR exists for `{branch}`, update it with `gh pr edit {branch} --title ... --body-file {pr_body}` and run `gh pr ready {branch}` instead of `gh pr create`.

- [ ] **Step 1: Write the failing tests**

```python
def test_owner_questions_reads_bullets_until_the_next_section():
    text = "## Calls made for the owner\n- a Rejected: b\n\n## Questions for the owner\n- Include REITs? Recommended: no\n- Cap? Recommended: 6%\n\n## Plan\n- not a question\n"
    assert owner_questions(text) == ["Include REITs? Recommended: no", "Cap? Recommended: 6%"]
    assert owner_questions("## Questions for the owner\n\n## Next\n") == []

def test_spec_with_owner_questions_parks_with_them_in_the_draft(tmp_path):
    reason, fake = full_item(tmp_path, spec_text=GOOD_SPEC + "\n## Questions for the owner\n- Include REITs? Recommended: no\n")
    body = fake.drafts()[-1][fake.drafts()[-1].index("--body") + 1]
    assert "owner questions in" in body and "- Include REITs? Recommended: no" in body

def test_pr_stage_with_only_a_draft_open_is_a_failure(tmp_path):
    reason, fake = run_fake(tmp_path, resume_branch="loop/row-a", open_prs=[{"number": 3, "isDraft": True}], stage="pr")
    assert any("pr stage reported ok but no ready PR exists" in line for line in fake.lines())
```

Run `uv run pytest tests/test_loop_state.py tests/test_loop_driver.py` and expect FAIL.
- [ ] **Step 2: Implement** the changes in the modules and prompts. Run the tests again and expect PASS.
- [ ] **Step 3: Commit** `git commit -am "feat(loop): owner questions park the item; resumed drafts are readied"`

### Task 8: Weekdays only

Model: haiku

**Files:**
- Modify: `src/kit/loop/driver.py`
- Test: `tests/test_loop_driver.py`

**Interfaces:**
- Consumes: `may_start` (task 5); `Env.now` and `Env.weekend_ok` (task 6).
- Produces: a new stop reason, `"weekend"`. `run`, `pick_only` and `_Run.work` check `env.weekend_ok or may_start(env.now())` before the probe, before the pick and before each stage, and return `"weekend"` when the check fails.

- [ ] **Step 1: Write the failing tests**

```python
def test_sunday_run_makes_no_claude_call(tmp_path):
    reason, fake = run_fake(tmp_path, now=lambda: datetime(2026, 10, 25, 10))
    assert reason == "weekend" and fake.stages == []

def test_stage_ending_on_saturday_is_followed_by_none(tmp_path):
    # FakeEnv.now returns Friday 23:00 until its claude() has run the spec stage, then Saturday 00:05
    reason, fake = run_fake(tmp_path, saturday_after="spec")
    assert reason == "weekend" and fake.stages == ["probe", "spec"]

def test_weekend_ok_overrides(tmp_path):
    reason, fake = run_fake(tmp_path, now=lambda: datetime(2026, 10, 25, 10), weekend_ok=True)
    assert "spec" in fake.stages
```

Run `uv run pytest tests/test_loop_driver.py -k "weekend or saturday or sunday"` and expect FAIL.
- [ ] **Step 2: Implement** the checks. Run the same tests and expect PASS.
- [ ] **Step 3: Commit** `git commit -am "feat(loop): start no stage on Saturday or Sunday"`

### Task 9: Snapshot holds the code, and the driver hands over

Model: sonnet

**Files:**
- Modify: `src/kit/snapshot.py`
- Create: `src/kit/loop/handover.py`
- Test: `tests/test_snapshot.py`, `tests/test_loop_handover.py`

**Interfaces:**
- Consumes: `parse_version` (`snapshot.py`), `parse_kitfile` (`kitfile.py`).
- Produces:
  - `tag_has_loop(kit_repo: Path, version: str, run: Runner) -> bool`: true when `git ls-tree -d <version> src/kit/loop` prints anything;
  - `export_src(kit_repo, version, work, stage, run) -> None`: `git archive <version>:src/kit` into `stage/src/kit`; `snapshot()` calls it before `install_snapshot` only when `tag_has_loop` is true;
  - `snapshot_src(kit_home: Path, version: str) -> Path`: `kit_home / version / "src"`;
  - `latest_applied(kit_json_text: str) -> str | None`: the last `applies[].version`, or `None` when there are no applies;
  - `handover_target(latest: str | None, running: str, kit_home: Path) -> Path | None`: the snapshot `src` path when `latest` is newer by semver than `running` (`"v" + kit.__version__`) and `<src>/kit/cli.py` exists, otherwise `None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_snapshot_of_a_tag_with_the_loop_holds_src(kit_repo, tmp_path):
    add_loop_package(kit_repo); tag(kit_repo, "v0.2.0", plugin_version="0.2.0")
    path = snapshot(kit_repo, "v0.2.0", tmp_path / "home", run)
    assert (path / "src/kit/loop/__init__.py").exists() and (path / "plugins/kit").is_dir()

def test_snapshot_of_a_tag_without_the_loop_has_no_src(kit_repo, tmp_path):
    assert not (snapshot(kit_repo, "v0.1.0", tmp_path / "home", run) / "src").exists()

def test_handover_only_to_a_newer_existing_snapshot(tmp_path):
    (tmp_path / "v0.3.0/src/kit").mkdir(parents=True); (tmp_path / "v0.3.0/src/kit/cli.py").write_text("")
    assert handover_target("v0.3.0", "v0.2.0", tmp_path) == tmp_path / "v0.3.0/src"
    assert handover_target("v0.2.0", "v0.2.0", tmp_path) is None
    assert handover_target("v0.4.0", "v0.2.0", tmp_path) is None
    assert handover_target(None, "v0.2.0", tmp_path) is None
```

Run `uv run pytest tests/test_snapshot.py tests/test_loop_handover.py` and expect FAIL.
- [ ] **Step 2: Implement** the changes. Run the same tests and expect PASS.
- [ ] **Step 3: Commit** `git commit -m "feat(snapshot): pinned loop code per version, and handover to a newer one"` (add the files).

### Task 10: `kit roadmap` and `kit loop` commands

Model: sonnet

**Files:**
- Create: `src/kit/roadmap_report.py`, `src/kit/loop_cmd.py`
- Modify: `src/kit/cli.py`
- Test: `tests/test_roadmap_report.py`, `tests/test_loop_cmd_parts.py`, `tests/test_cli_pipeline.py`

**Interfaces:**
- Consumes: tasks 1–9.
- Produces:
  - `roadmap_report.py`: `format_report(roadmap: Roadmap, result: Pick | None, prs: list[Pr] | None, gh_error: str = "") -> str`. It prints `Items: <n> open, <n> owner, ...` (every status, in `STATUSES` order), then `Next pick: <title>` (or `none`, or `unknown (gh: <reason>)`), then a `Skipped:` list as `- <title>: <reason>`, then `For you this weekend:` with the owner items as `- <title>: <blocked_by>` followed by the parked drafts as `- <url>: <reason>` plus their questions indented as `    - <question>`.
  - `loop_cmd.py` (wiring), with the extracted logic tested in `tests/test_loop_cmd_parts.py`:
    - `runtime_dir(kit_home, repo) -> Path`;
    - `require_loop(kit: KitFile | None) -> LoopConfig`: `KitError("<repo>/.claude/kit.json has no loop section")` when missing;
    - `program(repo: Path) -> list[str]`: `[<uv>, "run", "--no-project", "python", "-m", "kit.cli", "loop", "run", <repo>]`;
    - `resume(env: Env, key: str) -> None`: takes the lock, checks out `loop/<key>` from origin, refuses with `KitError("answer the questions in <spec> first")` while `owner_questions` is non-empty, refuses unless the status stage is `parked`, then writes stage `spec`, commits `chore(loop): <key> resume at spec` and pushes;
    - `install(repo, kit_home, agents_dir, launchctl: Runner | None) -> Path`: needs a `loop` section and a valid `docs/roadmap.md`; raises `KitError` naming each `other_loop_agents` plist together with "run its uninstall first (for dividend-growth: scripts/feature_loop.sh uninstall)"; needs the snapshot `src` of `latest_applied(<origin base kit.json>)`; writes the plist with `PYTHONPATH=<snapshot src>` and the same `PATH` building as `feature_loop.sh`'s `loop_path`; then, unless `launchctl` is `None`, runs bootout and bootstrap.
- CLI:
  - `kit roadmap <repo>`;
  - `kit loop run <repo> [--pick-only] [--weekend-ok] [--no-handover]`;
  - `kit loop install <repo> [--no-launchctl] [--launch-agents DIR]`;
  - `kit loop uninstall <repo>`;
  - `kit loop status <repo>`;
  - `kit loop resume <repo> <key>`.

  `run` builds the real `Env` the way dividend-growth's `_real_env` does, with `claude` going through `claude_command(stage, text, <runtime>/settings.json)` after writing `loop_settings(...)` there, and `now=datetime.now`. It does the handover first unless `--no-handover` is given.

- [ ] **Step 1: Write the failing UNIT tests** for `format_report`: one with every section present, one with `gh_error` that prints `Next pick: unknown (gh: not found)` and still prints the counts. Write the failing tests for `require_loop`, `program`, and `resume` refusing with open questions and with a non-parked stage. Use a FakeEnv over temp git repos with a bare origin.
- [ ] **Step 2: Write the failing PIPELINE tests** in `tests/test_cli_pipeline.py`:
  - `test_roadmap_prints_counts_and_next_pick`: a temp repo with `docs/roadmap.md`, and a fake `gh` script on `PATH` (via `monkeypatch.setenv`) that prints `[]`;
  - `test_roadmap_invalid_is_exit_1_with_the_line`;
  - `test_loop_install_writes_the_plist_and_refuses_an_old_agent`: `--no-launchctl --launch-agents <tmp>`, with a snapshot made by `snapshot()` from the fixture kit repo; the second run with a `com.dgi.feature-loop.plist` in the directory exits 1.
- [ ] **Step 3: Run** `uv run pytest tests/test_roadmap_report.py tests/test_loop_cmd_parts.py tests/test_cli_pipeline.py -k "roadmap or loop"`. Expect FAIL.
- [ ] **Step 4: Implement** the changes.
- [ ] **Step 5: Run** the same tests and expect PASS, then `uv run pytest -q`.
- [ ] **Step 6: Commit** `git commit -m "feat(cli): kit roadmap and kit loop run|install|uninstall|status|resume"` (add the files).

### Task 11: `kit apply` migrates the old loop and starts the roadmap

Model: sonnet

**Files:**
- Modify: `src/kit/migrate.py`, `src/kit/known_hashes.json`, `src/kit/gitops.py` (`pr_body`), `src/kit/apply.py`, `starter/CLAUDE.md`
- Create: `starter/docs/roadmap.md`
- Test: `tests/test_migrate.py`, `tests/test_gitops.py`, `tests/test_starter.py`

**Interfaces:**
- Produces:
  - `CANDIDATES` adds `scripts/feature_loop.py`, `scripts/feature_loop.sh`, `scripts/loop_prompts/{build,pick,plan,pr,probe,spec}.md` and `tests/test_feature_loop.py`;
  - `PROSE_PATTERN` adds `|feature_loop|loop_prompts`;
  - `roadmap_files(repo: Path) -> list[str]`: the tracked files under `docs/` whose name contains `roadmap`, plus `docs/next-steps.md` when present, minus `docs/roadmap.md`; sorted; via `git ls-files docs`;
  - `pr_body(..., to_convert: list[str], loop_notes: list[str])` adds a `### Roadmap to convert into docs/roadmap.md` section and a `### Loop` section, each only when non-empty;
  - `loop_notes(had_loop: bool, agents: list[Path], has_loop_section: bool) -> list[str]`, which gives, in this order: `before merging, run scripts/feature_loop.sh uninstall in the repo (loaded: <plist name>)` for each agent; `after merging, run kit loop install <repo>` when `had_loop`; `add a loop section to .claude/kit.json (see the spec)` when `had_loop` is true and `has_loop_section` false;
  - in `apply.py`, `had_loop` is true when `"scripts/feature_loop.py"` is in `migration.remove` or `migration.overrides`, and the agents come from `other_loop_agents(Path.home() / "Library/LaunchAgents", repo, loop_label(repo.name))` (read-only).
- `starter/docs/roadmap.md` holds the `# Roadmap` heading, a short intro (what each status means, that the loop takes only `open`, that `owner` items are the weekend list, and that the PR that lands an item sets `done` and fills in Spec, Plan and PR) and no items. `starter/CLAUDE.md` gets the line `Roadmap: docs/roadmap.md. The PR that lands an item sets its Status to done and fills in Spec, Plan and PR.`
- Regenerate `known_hashes.json` with `uv run python scripts/known_hashes.py ../dividend-growth ../investment > src/kit/known_hashes.json` (read-only on both repos). Then check that the existing v0.1.0 hashes are still present and that the 9 loop files were added.

- [ ] **Step 1: Write the failing tests:** dividend-growth's loop files with known hashes are removed; an edited `scripts/feature_loop.py` is kept as an override, and `had_loop` is still true; `roadmap_files` on a temp repo with `docs/superpowers/specs/2026-10-05-dgi-roadmap.md`, `docs/next-steps.md` and `docs/roadmap.md` gives the first two; `pr_body` prints both new sections and leaves out empty ones; `loop_notes` gives the order above.
- [ ] **Step 2: Run** `uv run pytest tests/test_migrate.py tests/test_gitops.py tests/test_starter.py`. Expect FAIL.
- [ ] **Step 3: Implement** the changes, and regenerate the hashes.
- [ ] **Step 4: Run** the same tests and expect PASS, then `uv run pytest -q`.
- [ ] **Step 5: Commit** `git commit -am "feat(apply): migrate the old loop, list roadmaps to convert, starter roadmap"` (add `starter/docs/roadmap.md` too).

### Task 12: Release docs for v0.2.0

Model: haiku

**Files:**
- Modify: `plugin/.claude-plugin/plugin.json`, `pyproject.toml`, `src/kit/__init__.py` (all to `0.2.0`), `CHANGELOG.md`, `docs/command.md`, `README.md`, `CLAUDE.md` (a `Spec` line for the new spec and plan)

- [ ] **Step 1: Write the changelog entry.** In `CHANGELOG.md`, add `## v0.2.0 — <date>` listing: `docs/roadmap.md` format and `kit roadmap`; `kit loop` with weekday runs, the pick in code, owner questions that park the item, and `resume`; snapshots that hold `src/kit`; dividend-growth's loop migrated; the `loop` section in `kit.json`.
- [ ] **Step 2: Update the commands doc.** Add every new command, with one line each, to `docs/command.md`, plus a "Loop" section: runtime directory, logs, how to resume a parked item.
- [ ] **Step 3: Check the tests.** Run `uv run pytest -q` and expect all PASS. `tests/test_plugin_files.py` checks that the versions agree.
- [ ] **Step 4: Commit** `git commit -am "docs: v0.2.0 changelog, commands and version"`.
- [ ] **Step 5 (Owner):** merge the branch into `main`, then run `git tag v0.2.0` on the merge commit.

### Task 13: Rollout (owner steps, from the spec's Rollout section)

Model: none (owner)

- [ ] **dividend-growth.** Commit or stash first. Then run `kit apply ../dividend-growth`.
- [ ] **Convert dividend-growth's roadmap** in a dividend-growth session, on the apply branch: convert `docs/superpowers/specs/2026-10-05-dgi-roadmap.md` and `docs/next-steps.md` into `docs/roadmap.md`. Keep the 7 in-flight titles verbatim. Replace the old files with a one-line pointer. Add the `loop` section (base `develop`, forbidden `../investment` and `../capital-trading`, read first `../investment/GOLD_SCHEMA.md`, and the how-to-guide PR step). Update CLAUDE.md and `docs/command.md`.
- [ ] **Check and swap the loop.** `kit roadmap ../dividend-growth` must pass and show the expected next pick. Run `scripts/feature_loop.sh uninstall`, merge the PR, then run `kit loop install ../dividend-growth`.
- [ ] **Watch the first weekday run.** `kit loop status ../dividend-growth` must show it resuming an in-flight `loop/*` branch.
- [ ] **investment.** Run `kit apply ../investment`, then convert the master plan and sketch into `docs/roadmap.md` in an investment session, and run `kit roadmap ../investment`. Do not install its loop yet.
