# kit v0.4.0 cross-repo requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any session, loop or interactive, can ask a sibling repo for a fix or feature by filing one `Status: owner` roadmap item as a PR on that repo, through code that can touch nothing else there.

**Architecture:** A pure module `kit/request.py` parses a request file, builds the filed item and appends it to the target's roadmap text. A wiring module `kit/request_cmd.py` does the git and gh work in a temporary worktree of the target taken from its `origin`. `kit request` (CLI) and the loop driver (through an injected callable) both call it. Outcomes for the loop are kept in `~/.claude/kit/loop/<repo>/requests.json` and copied into PR bodies.

**Tech Stack:** Python 3, argparse, dataclasses, `git` and `gh` through `kit.gitrun.Runner`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-cross-repo-requests-design.md`

## Global Constraints

- Follow `docs/code-conventions.md`: minimal functions, typed named results, `KitError` subclasses, a UNIT test file beside each module, PIPELINE tests only in `tests/test_cli_pipeline.py`. `cli.py` is wiring.
- Tests run offline: `git` on temp repos with a bare repo as `origin`, `gh` through an injected runner (UNIT) or a `fake_bin` shim (PIPELINE). Never read the real `~/.claude/projects/` or real sibling repos.
- `kit request` writes nothing in the requester repo. In the target it creates one temporary worktree under `<kit_home>/requests/`, commits only `docs/roadmap.md`, pushes one branch `request/<key>` and opens one PR. It never touches the target's checked-out branch, index or working tree, and removes the worktree and local branch afterwards, also on failure.
- Filed item fields: `Status: owner`, `Blocked by: the owner's review of a request from <requester>`, `Requested by: <requester>`. `Status`, `Blocked by`, `Requested by` and `Depends on` from the request file are dropped.
- Commit message `roadmap: request from <requester>: <title>` + blank line + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. PR title `request from <requester>: <title>`.
- Minimum target kit version: `v0.4.0` (`MIN_TARGET_VERSION`).
- Errors are one-line `KitError`s.
- The loop's `forbidden_paths` deny rules and generated settings do not change.
- Run tests with `uv run pytest -q`; `uv run mypy` must pass.

## Review Focus

- `kit apply` silently dropping the `requests` section when it rewrites `kit.json` (`apply.py:85` builds a new `KitFile`). Expect the section to survive an apply: Task 2 tests it.
- A `## Requests` section that already exists but is not the last section. Expect the item to land at the end of that section, not inside whatever section follows: Task 3 tests it.
- A failed filing leaving the target dirty: the worktree, or the local `request/<key>` branch, left behind so the next attempt fails with "branch already exists". Expect cleanup on every failure path: Task 5 tests push failure.
- The parked-PR body gaining a requests list after the questions list, which `parse_park_body` would then read as more questions. Expect the requests list before the questions: Task 6 tests it.
- A request file with no `Target:` line, or a `Target:` naming a repo not in `requests.targets`, written by a loop session. Expect a failed entry with the reason, the file deleted, and the stage carrying on: Task 7 tests it.

---

### Task 1: `Requested by` roadmap field

**Files:**
- Modify: `src/kit/roadmap.py` (`FIELDS`, `Item`, `_item`)
- Modify: `starter/docs/roadmap.md:18` (the "Other fields" line)
- Test: `tests/test_roadmap.py`

**Interfaces:**
- Produces: `Item.requested_by: str` (`""` when absent), the field name `"Requested by"` in `FIELDS`.

- [ ] **Step 1: Write the failing tests**

```python
def test_requested_by_is_a_field_on_any_status():
    text = "### A\n- Status: owner\n- Blocked by: review\n- Requested by: dividend-growth\n\n### B\n- Status: done\n- Requested by: investment\n"
    roadmap = parse_roadmap(text)
    assert [i.requested_by for i in roadmap.items] == ["dividend-growth", "investment"]

def test_requested_by_is_blank_when_absent():
    assert parse_roadmap("### A\n- Status: open\n").items[0].requested_by == ""
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_roadmap.py -q -k requested_by`
Expected: FAIL with `unknown field 'Requested by'`.

- [ ] **Step 3: Add `"Requested by"` to `FIELDS`, `requested_by: str` to `Item` (after `pr`, before `line`), fill it in `_item`**

In the starter roadmap's "Other fields" line add: `` `Requested by` (the sibling repo directory that asked for this item through `kit request`; set by the kit) ``.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (fix any test that builds `Item(...)` positionally).

- [ ] **Step 5: Commit**

```bash
git add src/kit/roadmap.py starter/docs/roadmap.md tests/
git commit -m "feat(roadmap): Requested by field"
```

---

### Task 2: `requests` section in `kit.json`

**Files:**
- Modify: `src/kit/kitfile.py`
- Modify: `src/kit/apply.py:85`
- Test: `tests/test_kitfile.py`

**Interfaces:**
- Produces: `RequestsConfig(targets: tuple[str, ...])`; `KitFile.requests: RequestsConfig | None = None` (after `loop`); `optional_requests(data: dict[str, Any]) -> RequestsConfig | None`; `with_apply` and `write_kitfile` keep `requests`.

- [ ] **Step 1: Write the failing tests**

```python
BASE = '{"test_command": "t", "applies": []'

def test_requests_section_is_parsed():
    kit = parse_kitfile(BASE + ', "requests": {"targets": ["../investment"]}}')
    assert kit.requests == RequestsConfig(("../investment",))

def test_no_requests_section_is_none():
    assert parse_kitfile(BASE + "}").requests is None

@pytest.mark.parametrize("raw, message", [
    ('"x"', "requests must be an object"),
    ('{"targets": "../a"}', "requests.targets must be a list of strings"),
    ('{"targets": [], "other": 1}', "requests has unknown key 'other'"),
])
def test_bad_requests_section(raw, message):
    with pytest.raises(KitError, match=message):
        parse_kitfile(BASE + f', "requests": {raw}}}')

def test_requests_survive_write_and_with_apply(tmp_path):
    kit = KitFile("t", (), None, RequestsConfig(("../investment",)))
    write_kitfile(tmp_path, with_apply(kit, Apply("v0.4.0", "c", "d")))
    assert read_kitfile(tmp_path).requests == RequestsConfig(("../investment",))
```

Also, in `tests/test_cli_pipeline.py`, extend the existing apply happy-path fixture's `kit.json` with a `requests` section and assert it is still there after `test_apply_puts_the_version_into_the_repo_on_a_branch` (one added assertion, not a new test).

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_kitfile.py -q -k requests`
Expected: FAIL with `ImportError: RequestsConfig`.

- [ ] **Step 3: Implement**

`REQUESTS_KEYS = frozenset({"targets"})`. Reuse `string_tuple`, generalised to take the section name for its message (`f"{section}.{key} must be a list of strings"`); keep loop messages unchanged. `write_kitfile` writes `"requests": {"targets": [...]}` after `loop` when set. In `apply.py:85` pass `kit.requests` as the fourth argument.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/kitfile.py src/kit/apply.py tests/
git commit -m "feat(kitfile): requests.targets section, kept by apply"
```

---

### Task 3: pure request logic

**Files:**
- Create: `src/kit/request.py`
- Test: `tests/test_request.py`

**Interfaces:**
- Consumes: `parse_roadmap`, `item_key`, `Roadmap`, `Item` (`kit.roadmap`); `parse_version` (`kit.snapshot`); `CO_AUTHOR` (`kit.loop.driver`).
- Produces:
  - `MIN_TARGET_VERSION = "v0.4.0"`, `REQUESTS_SECTION = "## Requests"`, `TARGET_PREFIX = "Target: "`
  - `class RequestError(KitError)`
  - `@dataclass(frozen=True) class Request: target: str; title: str; key: str; fields: tuple[tuple[str, str], ...]; body: str` (`target` is `""` without a `Target:` line; `fields` holds only kept fields)
  - `parse_request(text: str) -> Request`
  - `filed_item(request: Request, requester: str) -> str`
  - `with_request(roadmap_text: str, item_text: str) -> str` (raises `RoadmapError` when the result does not validate)
  - `existing_item(roadmap: Roadmap, key: str) -> Item | None`
  - `allowed_target(repo: Path, targets: tuple[str, ...], target: Path) -> Path`
  - `target_by_name(repo: Path, targets: tuple[str, ...], name: str) -> Path`
  - `require_version(latest: str | None, target_name: str) -> None`
  - `commit_message(requester: str, title: str) -> str`, `pr_title(requester: str, title: str) -> str`, `pr_body(item_text: str, requester: str, loop_branch: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
REQ = "Target: investment\n### Fix FX rates\n- Status: open\n- Depends on: Other\n- Spec: docs/x.md\n\nRates are stale.\n"

def test_parse_request_reads_target_title_kept_fields_and_body():
    r = parse_request(REQ)
    assert (r.target, r.title, r.key) == ("investment", "Fix FX rates", "fix-fx-rates")
    assert r.fields == (("Spec", "docs/x.md"),) and r.body == "Rates are stale."

def test_parse_request_without_target_line():
    assert parse_request("### A\n\nbody\n").target == ""

@pytest.mark.parametrize("text, message", [
    ("just text\n", "no ### item"),
    ("### A\n\n### B\n", "exactly one ### item"),
    ("## Section\n### A\n", "no ## section"),
])
def test_parse_request_rejects(text, message):
    with pytest.raises(RequestError, match=message):
        parse_request(text)

def test_filed_item_sets_owner_fields():
    assert filed_item(parse_request(REQ), "dividend-growth") == (
        "### Fix FX rates\n- Status: owner\n"
        "- Blocked by: the owner's review of a request from dividend-growth\n"
        "- Requested by: dividend-growth\n- Spec: docs/x.md\n\nRates are stale.\n"
    )

def test_with_request_creates_the_section_at_the_end():
    out = with_request("## Now\n\n### A\n- Status: open\n", "### B\n- Status: open\n")
    assert out.endswith("\n## Requests\n\n### B\n- Status: open\n")
    assert parse_roadmap(out).by_title("B").section == "Requests"

def test_with_request_appends_inside_an_existing_requests_section_that_is_not_last():
    text = "## Requests\n\n### A\n- Status: open\n\n## Later\n\n### C\n- Status: open\n"
    out = with_request(text, "### B\n- Status: open\n")
    assert parse_roadmap(out).by_title("B").section == "Requests"
    assert out.index("### B") < out.index("## Later")

def test_with_request_that_does_not_validate_raises():
    with pytest.raises(RoadmapError, match="unknown field 'Colour'"):
        with_request("", "### B\n- Status: open\n- Colour: red\n")

def test_allowed_target_resolves_relative_to_repo(tmp_path):
    repo, inv = tmp_path / "dg", tmp_path / "investment"
    assert allowed_target(repo, ("../investment",), inv) == inv.resolve()
    with pytest.raises(KitError, match="not in requests.targets"):
        allowed_target(repo, ("../investment",), tmp_path / "capital-trading")

def test_target_by_name(tmp_path):
    assert target_by_name(tmp_path / "dg", ("../investment",), "investment") == (tmp_path / "investment").resolve()
    with pytest.raises(KitError, match="'capital-trading' is not in requests.targets"):
        target_by_name(tmp_path / "dg", ("../investment",), "capital-trading")
    with pytest.raises(KitError, match="no Target: line"):
        target_by_name(tmp_path / "dg", ("../investment",), "")

@pytest.mark.parametrize("latest", ["v0.3.0", None])
def test_require_version_refuses_old_targets(latest):
    with pytest.raises(KitError, match="apply v0.4.0 or later to investment first"):
        require_version(latest, "investment")

def test_require_version_accepts_v0_4_0():
    require_version("v0.4.0", "investment")

def test_texts():
    assert commit_message("dg", "T") == f"roadmap: request from dg: T\n\n{CO_AUTHOR}"
    assert pr_title("dg", "T") == "request from dg: T"
    body = pr_body("### T\n", "dg", "loop/x")
    assert "### T" in body and "dg" in body and "loop/x" in body and body.rstrip().endswith(ATTRIBUTION)
```

(`ATTRIBUTION` from `kit.loop.prs`; `pr_body` with `loop_branch=""` omits the loop line.)

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_request.py -q`
Expected: FAIL with `ModuleNotFoundError: kit.request`.

- [ ] **Step 3: Implement `src/kit/request.py`**

`parse_request` strips a first line starting with `TARGET_PREFIX`, then reads field lines with the same `- Name: value` pattern as `kit.roadmap` and drops `("Status", "Blocked by", "Requested by", "Depends on")`. `with_request` inserts the item, separated by one blank line, before the first `## ` heading after `## Requests`, or at the end of the file (adding `\n## Requests\n\n` when the section is missing), then calls `parse_roadmap` on the result and returns it. `existing_item` matches by key. `require_version` treats `None` as too old. Error messages are the strings the tests match.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_request.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/request.py tests/test_request.py
git commit -m "feat(request): parse, build and append a cross-repo request"
```

---

### Task 4: runtime log of the loop's requests

**Files:**
- Create: `src/kit/loop/requests.py`
- Test: `tests/test_loop_requests.py`

**Interfaces:**
- Produces:
  - `REQUESTS_FILE = "requests.json"`, `REQUESTS_HEADING = "## Requests filed on other repos"`
  - `@dataclass(frozen=True) class RequestRecord: target: str; title: str; url: str = ""; error: str = ""`
  - `read_requests(runtime: Path, branch: str) -> list[RequestRecord]`
  - `add_requests(runtime: Path, branch: str, records: list[RequestRecord]) -> None`
  - `request_lines(records: list[RequestRecord]) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
def test_records_are_kept_per_branch_and_appended(tmp_path):
    add_requests(tmp_path, "loop/a", [RequestRecord("investment", "T", url="https://x/1")])
    add_requests(tmp_path, "loop/a", [RequestRecord("investment", "U", error="refused")])
    add_requests(tmp_path, "loop/b", [RequestRecord("investment", "V", url="https://x/2")])
    assert [r.title for r in read_requests(tmp_path, "loop/a")] == ["T", "U"]
    assert json.loads((tmp_path / "requests.json").read_text())["loop/b"] == [{"target": "investment", "title": "V", "url": "https://x/2"}]

def test_no_file_is_no_records(tmp_path):
    assert read_requests(tmp_path, "loop/a") == []

def test_request_lines():
    assert request_lines([RequestRecord("investment", "T", url="u"), RequestRecord("investment", "U", error="why")]) == [
        "- filed on investment: T: u", "- failed on investment: U: why",
    ]
```

(Entries store `url` or `error`, not both, as the spec's `{target, title, url}` / `{target, title, error}`.)

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_loop_requests.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/kit/loop/requests.py`** (create `runtime` if missing; `sort_keys=True`, indent 2)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_loop_requests.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/loop/requests.py tests/test_loop_requests.py
git commit -m "feat(loop): runtime requests.json of filed requests"
```

---

### Task 5: filing a request on the target (git and gh)

**Files:**
- Create: `src/kit/request_cmd.py`
- Modify: `src/kit/loop/handover.py` (receives `origin_latest`), `src/kit/loop_cmd.py` (imports it from there)
- Test: `tests/test_request_cmd.py`; move the `origin_latest` tests from `tests/test_loop_cmd_parts.py` to `tests/test_loop_handover.py`

**Interfaces:**
- Consumes: everything from Task 3; `RequestRecord` (Task 4); `read_kitfile`, `KITFILE` (`kit.kitfile`); `Runner` (`kit.gitrun`).
- Produces:
  - `origin_latest(repo: Path, base_branch: str, runner: Runner) -> str`, now in `kit.loop.handover`, body unchanged.
  - `target_base(target: Path, run: Runner) -> str`
  - `@dataclass(frozen=True) class Filed: target: str; title: str; url: str`
  - `file_request(requester: Path, target: Path, request: Request, kit_home: Path, run: Runner, loop_branch: str = "") -> Filed`
  - `file_request_file(requester: Path, targets: tuple[str, ...], kit_home: Path, run: Runner, path: Path, loop_branch: str) -> RequestRecord` (never raises `KitError`; returns an `error` record instead)

- [ ] **Step 1: Write the failing tests**

Fixture `pair(tmp_path)`: a bare `origin.git`, a target clone `investment/` with `.claude/kit.json` (applies `v0.4.0`, no loop section), `docs/roadmap.md` (`"## Now\n\n### A\n- Status: open\n"`), pushed to `main`, `git remote set-head origin -a`; a requester dir `dividend-growth/` beside it. Runner `gh_fake(prs="[]")`: records `gh` calls and answers `gh pr list` with `prs` and `gh pr create` with `https://github.com/o/investment/pull/9`; everything else goes to `kit.gitrun.run`. Use `tests/builders.git` for setup.

```python
def test_file_request_pushes_one_roadmap_commit_and_opens_a_pr(pair, tmp_path):
    requester, target, origin = pair
    filed = file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh := gh_fake())
    assert filed == Filed("investment", "Fix FX rates", "https://github.com/o/investment/pull/9")
    changed = run(["git", "diff", "--name-only", "main", "request/fix-fx-rates"], origin).split()
    assert changed == ["docs/roadmap.md"]
    roadmap = parse_roadmap(run(["git", "show", "request/fix-fx-rates:docs/roadmap.md"], origin))
    item = roadmap.by_title("Fix FX rates")
    assert (item.status, item.requested_by, item.section) == ("owner", "dividend-growth", "Requests")
    create = next(c for c in gh.calls if c[:3] == ["gh", "pr", "create"])
    assert create[create.index("--base") + 1] == "main" and "request from dividend-growth: Fix FX rates" in create

def test_file_request_leaves_the_target_checkout_and_kit_home_clean(pair, tmp_path):
    requester, target, _ = pair
    (target / "scratch.txt").write_text("owner's work")
    before = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], target)
    file_request(requester, target, parse_request(REQ), tmp_path / "kit", gh_fake())
    assert run(["git", "rev-parse", "--abbrev-ref", "HEAD"], target) == before
    assert run(["git", "status", "--porcelain"], target).strip() == "?? scratch.txt"
    assert "request/" not in run(["git", "branch", "--list"], target)
    assert run(["git", "worktree", "list"], target).count("\n") == 1
    assert not any((tmp_path / "kit" / "requests").iterdir())

def test_a_failed_push_still_removes_worktree_and_branch(pair, tmp_path):
    # runner that raises KitError on `git push`
    ...
    assert "request/" not in run(["git", "branch", "--list"], target)
    assert run(["git", "worktree", "list"], target).count("\n") == 1

def test_refuses_a_title_already_on_the_base_roadmap(pair, tmp_path):
    with pytest.raises(KitError, match="already has 'A'"):
        file_request(requester, target, parse_request("### A\n"), tmp_path / "kit", gh_fake())

def test_refuses_when_an_open_request_pr_exists(pair, tmp_path):
    with pytest.raises(KitError, match="https://x/pull/3"):
        file_request(..., gh_fake(prs='[{"url": "https://x/pull/3"}]'))

def test_refuses_a_target_below_v0_4_0(pair, tmp_path):
    # kit.json on origin/main applies v0.3.0
    with pytest.raises(KitError, match="apply v0.4.0 or later to investment first"): ...

def test_refuses_a_target_without_kit_json(pair, tmp_path): ...       # match "no .claude/kit.json"
def test_refuses_a_target_with_an_invalid_roadmap(pair, tmp_path): ...  # match "docs/roadmap.md"

def test_target_base_prefers_the_loop_base_branch(pair):
    # target kit.json with {"loop": {"base_branch": "develop"}}, origin has develop
    assert target_base(target, run) == "develop"

def test_target_base_falls_back_to_origin_head(pair):
    assert target_base(target, run) == "main"

def test_file_request_file_turns_errors_into_a_record(pair, tmp_path):
    path = tmp_path / "r.md"
    path.write_text("Target: capital-trading\n### X\n")
    record = file_request_file(requester, ("../investment",), tmp_path / "kit", gh_fake(), path, "loop/a")
    assert record == RequestRecord("capital-trading", "X", error=ANY) and "not in requests.targets" in record.error

def test_file_request_file_with_an_unparsable_file_names_the_file(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("nothing\n")
    record = file_request_file(tmp_path, ("../investment",), tmp_path / "kit", gh_fake(), path, "")
    assert (record.title, record.url) == ("r.md", "") and "no ### item" in record.error
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_request_cmd.py -q`
Expected: FAIL with `ModuleNotFoundError: kit.request_cmd`.

- [ ] **Step 3: Move `origin_latest` to `kit/loop/handover.py`**, update `loop_cmd.py`'s import and move its three tests. Run `uv run pytest tests/test_loop_handover.py tests/test_loop_cmd_parts.py -q`: PASS.

- [ ] **Step 4: Implement `src/kit/request_cmd.py`**

`file_request` in order, each step its own small function:
1. `read_kitfile(target)` is `None` → `KitError(f"{target / KITFILE} not found")`.
2. `target_base`: `git fetch origin` in `target`; the target kit file's `loop.base_branch` if it has a loop section, else `git symbolic-ref --short refs/remotes/origin/HEAD` minus `origin/` (on failure: `KitError(f"{target.name} has no origin/HEAD; run git remote set-head origin -a there")`).
3. `require_version(origin_latest(target, base, run), target.name)`.
4. Base roadmap from `git show origin/<base>:docs/roadmap.md`, parsed (a missing file or `RoadmapError` → `KitError(f"{target.name} has no valid docs/roadmap.md on origin/{base}: <first line>")`).
5. `existing_item` → `KitError(f"{target.name} already has {title!r} (line N)")`; `gh pr list --head request/<key> --state open --json url` in `target` → `KitError(f"open request PR already exists: <url>")`.
6. A context manager `request_worktree(target, base, key, kit_home, run) -> Iterator[Path]`: path `<kit_home>/requests/<target.name>-<key>`; `git worktree add -b request/<key> <path> origin/<base>` in `target`; in `finally`, `git worktree remove --force <path>` then `git branch -D request/<key>`, both in `target`.
7. Inside it: write `with_request(base_text, filed_item(request, requester.name))` to `docs/roadmap.md`; `git add docs/roadmap.md`; `git commit -m commit_message(...)`; `git push -u origin request/<key>`; `gh pr create --base <base> --head request/<key> --title pr_title(...) --body pr_body(...)`; the URL is the last output line.

`file_request_file` reads `path`, parses it, resolves `target_by_name(requester, targets, request.target)` and calls `file_request`; any `KitError` becomes `RequestRecord(target, title or path.name, error=str(error))`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_request_cmd.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kit/request_cmd.py src/kit/loop/handover.py src/kit/loop_cmd.py tests/
git commit -m "feat(request): file a request as a PR from a temporary worktree of the target"
```

---

### Task 6: `kit request` command

**Files:**
- Modify: `src/kit/cli.py`
- Modify: `docs/command.md`
- Test: `tests/test_cli.py` (parser), `tests/test_cli_pipeline.py` (one happy path)

**Interfaces:**
- Consumes: `file_request` (Task 5), `parse_request`, `allowed_target` (Task 3), `read_kitfile`.
- Produces: `kit request <requester-repo> <target-repo> <request-file> [--kit-home DIR]`; prints the PR URL.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py`: `build_parser().parse_args(["request", "a", "b", "r.md"])` has `command == "request"` and `kit_home == KIT_HOME`.

In `tests/test_cli.py` (UNIT for the one branch the command has): a requester without a `requests` section exits 1 with `has no requests section` on stderr.

In `tests/test_cli_pipeline.py`:

```python
def test_request_files_a_pr_on_the_target(tmp_path, monkeypatch, capsys):
    # requester with kit.json requests.targets ["../investment"], target pair as in Task 5,
    # fake_bin(tmp_path, monkeypatch, {"gh": <prints [] for 'pr list', the URL for 'pr create'>})
    assert main(["request", str(requester), str(target), str(req), "--kit-home", str(tmp_path / "kit")]) == 0
    assert capsys.readouterr().out.strip() == "https://github.com/o/investment/pull/9"
    assert run(["git", "status", "--porcelain"], requester).strip() == ""
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_cli.py tests/test_cli_pipeline.py -q -k request`
Expected: FAIL (`invalid choice: 'request'`).

- [ ] **Step 3: Implement `request_command(args) -> int` in `cli.py`** and register it in `COMMANDS`

Wiring only: resolve both repos; a requester kit file with `requests is None` raises `KitError(f"{requester / KITFILE} has no requests section")` (put that check in a function `require_requests(kit: KitFile | None, repo: Path) -> RequestsConfig` in `kitfile.py`, tested in `tests/test_kitfile.py`, and have the CLI test above go through it); `allowed_target`; `file_request(..., run)`; print `filed.url`.

In `docs/command.md`, add `kit request <requester-repo> <target-repo> <request-file> [--kit-home DIR]` to the command block and a bullet: what the request file holds (`### <title>`, optional fields, body), that the item lands as `Status: owner` in `## Requests` of the target, that only targets in `requests.targets` on v0.4.0+ are accepted, and that it writes nothing in the requester.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/cli.py src/kit/kitfile.py docs/command.md tests/
git commit -m "feat(cli): kit request"
```

---

### Task 7: loop driver files requests

**Files:**
- Modify: `src/kit/loop/driver.py`, `src/kit/loop/prs.py` (`park_body`), `src/kit/loop/prompts/pr.md`, `src/kit/loop_cmd.py` (`real_env`)
- Test: `tests/test_loop_driver.py`, `tests/test_loop_prs.py`

**Interfaces:**
- Consumes: `RequestRecord`, `add_requests`, `read_requests`, `request_lines`, `REQUESTS_HEADING` (Task 4); `file_request_file` (Task 5, bound in `loop_cmd`); `Item.requested_by` (Task 1).
- Produces:
  - `Env.request_targets: tuple[str, ...] = ()` (target names, e.g. `("investment",)`)
  - `Env.file_request: Callable[[Path, str], RequestRecord] | None = None` (request file, loop branch)
  - `park_body(reason, spec, plan, questions, requests: list[str] = [])` — the requests block (`REQUESTS_HEADING`, blank line, lines) goes before the questions block.
  - new prompt fields `{requests_filed}` and `{requested_by}`.

- [ ] **Step 1: Write the failing tests**

Extend `FakeEnv`: an optional `request_targets` and a `file_request` that records `(path.read_text(), branch)` and returns `RequestRecord("investment", <title>, url="https://x/req/1")` (or a canned error record); a `step(...)` dict may carry `requests: dict[str, str]`, which `FakeEnv.claude` writes into `env.scratch / "requests"` before returning.

```python
def test_rules_name_the_requests_dir_and_targets_only_when_set(tmp_path):
    env = replace(env_with(LoopConfig("develop")), request_targets=("investment",))
    text = render("build", env)
    assert "/requests" in text and "`Target: <repo>`" in text and "investment" in text and "Never write to the other repo" in text
    assert "Target:" not in render("build", env_with(LoopConfig("develop")))

def test_request_files_written_by_a_stage_are_filed_logged_and_deleted(tmp_path):
    _, f = run_fake(tmp_path, request_targets=("investment",), spec=[step(requests={"a.md": "Target: investment\n### Fix\n"})], ...)
    assert f.filed == [("Target: investment\n### Fix\n", "loop/row-a")]
    assert not any((f.runtime / "scratch" / "requests").iterdir())
    assert read_requests(f.runtime, "loop/row-a")[0].url == "https://x/req/1"

def test_a_failed_request_does_not_fail_the_stage(tmp_path):
    # file_request returns an error record; the item still reaches its PR
    ...
    assert read_requests(f.runtime, "loop/row-a")[0].error

def test_pr_prompt_carries_requests_filed_and_requested_by(tmp_path):
    # roadmap item Row A has "- Requested by: dividend-growth"; requests.json has one record for the branch
    # inspect the rendered pr prompt the fake claude received
    assert "dividend-growth" in pr_prompt and "- filed on investment: Fix: https://x/req/1" in pr_prompt

def test_requests_filed_during_the_pr_stage_are_commented_on_the_pr(tmp_path):
    # pr step writes a request file and opens the PR
    assert any(c[:3] == ["gh", "pr", "comment"] for c in f.cmds)

def test_parked_draft_lists_the_requests(tmp_path):
    # a stage files a request then parks
    assert "## Requests filed on other repos" in body and "https://x/req/1" in body
```

In `tests/test_loop_prs.py`:

```python
def test_park_body_lists_requests_before_questions_and_questions_still_parse():
    body = park_body("needs fix", "s.md", "p.md", ["Q?"], ["- filed on investment: T: u"])
    assert body.index(REQUESTS_HEADING) < body.index(QUESTIONS_HEADING)
    assert parse_park_body(body).questions == ("Q?",)
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_loop_driver.py tests/test_loop_prs.py -q -k "request or requests"`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `_rules(config, targets, requests_dir)`: when `targets` is set, append `to ask another repo for a fix or a feature, write one roadmap item per file into `<requests_dir>`, its first line `Target: <repo>` (one of `investment`), then the `### <title>` item; the driver files it as a PR on that repo. Never write to the other repo. If the item cannot go on without that fix, reply `LOOP: park` with a reason that names the request` (targets ticked with `_ticked`). `requests_dir` is `env.scratch / "requests"`.
- `step`: create the requests dir before the session; after `_push_if_ahead`, call `_file_requests(env, branch) -> list[RequestRecord]`: each `*.md` file in sorted order goes through `env.file_request`, is deleted, and the records go to `add_requests(env.runtime, branch, ...)`; log one line per record. When `stage == "pr"` and records were filed and the branch has an open PR, write the lines to `env.runtime / "requests-comment.md"` and run `gh pr comment <number> --body-file <that file>`. With `env.file_request is None`, do nothing.
- PR fields in `step` for `stage == "pr"`: `requests_filed` = `"\n".join(request_lines(read_requests(...)))` or `"- none"`; `requested_by` = the worktree roadmap item's `requested_by` (`""` when the roadmap or item cannot be read).
- `_open_draft` passes `request_lines(read_requests(env.runtime, branch))` to `park_body`.
- `pr.md`: in the body list add a section "Requests filed on other repos" containing `{requests_filed}` verbatim; add a line: `Requested by: `{requested_by}` (blank means none). When it is not blank, the first line of the body is `Requested by {requested_by}: after merging, update its roadmap.``
- `loop_cmd.real_env`: read `kit.requests`; set `request_targets` to the target directory names and `file_request` to a closure over `file_request_file(repo, targets, kit_home, run, path, branch)`. `real_env` gains `requests: RequestsConfig | None` and `kit_home: Path` parameters; update its two callers.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/loop/ src/kit/loop_cmd.py tests/
git commit -m "feat(loop): file request files after each stage and report them in PRs"
```

---

### Task 8: `kit roadmap` reminds the owner to tell the requester

**Files:**
- Modify: `src/kit/roadmap.py` (`requester_roadmaps`), `src/kit/roadmap_report.py`, `src/kit/cli.py` (`roadmap_command`)
- Test: `tests/test_roadmap.py`, `tests/test_roadmap_report.py`

**Interfaces:**
- Consumes: `Item.requested_by`.
- Produces: `requester_roadmaps(repo: Path, roadmap: Roadmap) -> dict[str, Roadmap | None]` (one entry per distinct `requested_by` of a `done` item; `None` when `repo.parent / name` has no readable, valid roadmap); `format_report(roadmap, result, prs, gh_error="", requesters: dict[str, Roadmap | None] | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# test_roadmap_report.py
DONE = parse_roadmap("### Fix\n- Status: done\n- Requested by: dg\n\n### Other\n- Status: done\n")

def test_weekend_lists_done_requests_the_requester_has_not_marked_done():
    requester = parse_roadmap("### Fix\n- Status: owner\n- Blocked by: waiting\n")
    text = format_report(DONE, None, [], requesters={"dg": requester})
    assert "- Tell dg: Fix is done" in text and "Other" not in text.split("For you this weekend:")[1]

def test_a_requester_with_the_item_done_clears_it():
    text = format_report(DONE, None, [], requesters={"dg": parse_roadmap("### Fix\n- Status: done\n")})
    assert "Tell dg" not in text

def test_an_unreadable_requester_roadmap_is_named():
    assert "- Tell dg: Fix is done (requester roadmap not found)" in format_report(DONE, None, [], requesters={"dg": None})

# test_roadmap.py
def test_requester_roadmaps_reads_siblings(tmp_path):
    (tmp_path / "dg" / "docs").mkdir(parents=True)
    (tmp_path / "dg" / "docs" / "roadmap.md").write_text("### Fix\n- Status: done\n")
    found = requester_roadmaps(tmp_path / "inv", parse_roadmap("### Fix\n- Status: done\n- Requested by: dg\n\n### X\n- Status: done\n- Requested by: gone\n"))
    assert found["dg"].by_title("Fix").status == "done" and found["gone"] is None
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_roadmap.py tests/test_roadmap_report.py -q -k "requester or Tell or tell"`
Expected: FAIL.

- [ ] **Step 3: Implement**

`requester_roadmaps` catches `KitError` (which covers `RoadmapError`) per sibling and stores `None`. In `roadmap_report._weekend`, after the owner items, add the "Tell" lines; an item clears when the requester roadmap has a `done` item with the same title. `roadmap_command` passes `requester_roadmaps(repo, roadmap)`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/roadmap.py src/kit/roadmap_report.py src/kit/cli.py tests/
git commit -m "feat(roadmap): remind the owner to tell the requesting repo"
```

---

### Task 9: apply note, starter lines, kit docs

**Files:**
- Modify: `src/kit/migrate.py` (`isolation_notes`), `src/kit/apply.py` (adds them to `prose`)
- Modify: `starter/CLAUDE.md`, `CLAUDE.md` (kit), `CHANGELOG.md`
- Test: `tests/test_migrate.py`, `tests/test_starter.py` if it pins starter text

**Interfaces:**
- Produces: `isolation_notes(repo: Path, targets: tuple[str, ...]) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_isolation_notes_flag_an_unqualified_never_write_line(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# X\n\n- Never write to `../investment` from here.\n")
    assert isolation_notes(tmp_path, ("../investment",)) == [
        'CLAUDE.md:3: add "except a roadmap request through kit request"'
    ]

def test_isolation_notes_skip_qualified_lines_and_no_targets(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Never write to ../investment, except a roadmap request through `kit request`.\n")
    assert isolation_notes(tmp_path, ("../investment",)) == []
    assert isolation_notes(tmp_path, ()) == []
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_migrate.py -q -k isolation`
Expected: FAIL.

- [ ] **Step 3: Implement**

`isolation_notes` matches each `CLAUDE.md` line case-insensitively for `never write to` followed by the target's directory name, optionally in backticks and with `../`, and skips lines containing `kit request`. No `CLAUDE.md` → `[]`. In `apply.py`, `prose = prose_outside(...) + isolation_notes(repo, kit.requests.targets if kit.requests else ())`.

Text changes:
- `starter/CLAUDE.md`, under "Working conventions": `To ask another repo for a fix or a feature, write the item to a file in the scratch folder and run `kit request` (see the kit's `docs/command.md`); never edit another repo's files. Show the PR URL in your reply.` Extend the roadmap line with: `If the item has `Requested by`, tell the owner to update that repo's roadmap.`
- Kit `CLAUDE.md` Global Constraints: add `- `request` writes nothing in the requester; in the target it only creates a temporary worktree under `~/.claude/kit/requests/`, pushes one `request/<key>` branch and opens one PR adding one item to `docs/roadmap.md`.` and change the dividend-growth line to `Never write to `../investment` or `../capital-trading` from a dividend-growth session, except a roadmap request to investment through `kit request`.`
- `CHANGELOG.md`: an `## Unreleased` section at the top listing `kit request`, the `Requested by` field, the `requests.targets` section, loop request files and the `kit roadmap` reminder, in the style of the v0.3.0 entry.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kit/migrate.py src/kit/apply.py starter/CLAUDE.md CLAUDE.md CHANGELOG.md tests/
git commit -m "docs: kit request in the starter, the kit constraints and the changelog"
```

---

## After the plan

Rollout follows the spec's "Rollout" section and is the owner's: release v0.4.0 with the `releasing-claude-kit` skill, apply it to investment and merge, then apply it to dividend-growth, add `"requests": {"targets": ["../investment"]}` and fix its CLAUDE.md isolation line in a dividend-growth session.
