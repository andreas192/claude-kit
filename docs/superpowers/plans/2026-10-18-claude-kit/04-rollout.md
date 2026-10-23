# Phase 4: release and first rollout (tasks 15–16)

Index and global constraints: `../2026-10-18-claude-kit.md`. Spec: "First rollout". Steps marked **Owner** are done by the owner, not by an agent.

### Task 15: Release notes and v0.1.0

Model: haiku

**Files:**
- Create: `README.md`, `CHANGELOG.md`

- [ ] **Step 1:** `README.md` (under 60 lines): what the kit is (spec "Why", one paragraph), what it contains (spec table "What the kit contains"), the three commands with one example each from `docs/command.md`, and "Agents are `kit:implementer-haiku`, `kit:implementer-sonnet`, `kit:reviewer-sonnet`."
- [ ] **Step 2:** `CHANGELOG.md` with a `v0.1.0 — 2026-10-18` entry: the contents above; "Same behaviour as dividend-growth's local agents and hooks, except: agents read `test_command` from `.claude/kit.json`; `context-warn` names `docs/token-strategy.md` only when the repo has it, and its env var is `KIT_CONTEXT_WARN_STEP`; the test-layer guard reads `.claude/test-layers.json`, and in investment it no longer denies `import invest.cli_<name>` (the old regex lacked `\b`)."
- [ ] **Step 3: Run** `uv run pytest` — expect PASS.
- [ ] **Step 4: Commit** `git add README.md CHANGELOG.md && git commit -m "docs: README and v0.1.0 changelog"`.
- [ ] **Step 5 (Owner):** run `claude plugin validate ./plugin` — expect `Validation passed`. Merge the branch into `main`, then `git tag v0.1.0` on `main`.

### Task 16: Apply to dividend-growth (investment stays the control)

Model: sonnet (steps 2–3 run in a session inside dividend-growth, never in claude-kit or investment)

**Files (in dividend-growth, on branch `chore/claude-kit-v0.1.0`):**
- Modify by hand: every `path:line` the PR's "Edit by hand on this branch" section lists. Expected: `CLAUDE.md` (Testing: the hook is the kit's; Layout: drop `token_report.py` from `scripts/`), `docs/token-strategy.md` (Model routing: `kit:` agent names and "plugin agents" instead of `.claude/agents/`; Checkpoints: the kit's `context-warn`; Benchmarks: `kit bench <repo> --control ../investment`), `docs/command.md` ("Token benchmarks": the `kit bench` commands; "Feature loop": `kit bench` includes the loop's sessions).
- Check: `scripts/feature_loop.py` and `.claude/loop-settings.json` for agent names or `token_report` (the PR list covers tracked files; the loop's allow list needs `Bash(uv run --project ../claude-kit kit bench*)` only if the loop runs bench, which it does not today).

- [ ] **Step 1 (Owner):** in dividend-growth on a clean `main`, run `uv run --project ../claude-kit kit apply . --version v0.1.0`. Expect exit 0 and a PR URL; read the PR summary.
- [ ] **Step 2:** on that branch, make the hand edits listed above; run `uv run pytest -q` — expect PASS; commit `docs: point to the claude-kit agents, hooks and kit bench`; push.
- [ ] **Step 3 (Owner):** merge the PR. Start a fresh session in dividend-growth and check: `/plugin` lists `kit@kit-v0-1-0` enabled; `/agents` lists the three `kit:` agents and no local copies; asking Claude to write `from dgi.cli import app` into `tests/test_probe.py` is denied once (one denial, not two), then discard the probe.
- [ ] **Step 4 (Owner):** run `uv run --project ../claude-kit kit bench . --control ../investment`. Expect a `pre-kit` and a `v0.1.0` column, with `not enough data` in the Δ cells until v0.1.0 has 5 sessions.
- [ ] **Step 5 (Owner):** after at least 5 dividend-growth sessions on v0.1.0, run bench again (the B and F rows should show a Δ close to zero, since v0.1.0 does not change behaviour), then apply v0.1.0 to investment from a terminal or a session inside investment: `uv run --project ../claude-kit kit apply ../investment --version v0.1.0`. Its PR should list `guard.mjs` as untouched and its two one-task implementer agents as removed.
