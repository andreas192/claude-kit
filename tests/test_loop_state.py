"""UNIT: kit.loop.state, the per-branch status file and the stage order."""

import pytest

from kit.loop.prs import Pr
from kit.loop.state import (
    Status,
    has_calls_section,
    is_live,
    new_status,
    next_stage,
    owner_questions,
    read_status,
    resume_stage,
    unfinished,
    write_status,
)


def test_unfinished_is_a_loop_branch_without_pr():
    prs = [Pr(6, "loop/a", "OPEN", "2026-10-17", "u")]
    assert unfinished(["loop/c", "loop/a", "loop/b"], prs) == "loop/b"
    assert unfinished(["loop/a"], prs) is None


def test_unfinished_includes_a_live_branch_with_a_pr():
    prs = [Pr(6, "loop/a", "MERGED", "2026-10-17", "u")]
    assert unfinished(["loop/a"], prs, live={"loop/a"}) == "loop/a"


@pytest.mark.parametrize(
    ("raw", "live"),
    [('{"stage": "build"}', True), ('{"stage": "spec"}', True), ('{"stage": "parked"}', False), (None, False)],
)
def test_is_live(raw, live):
    assert is_live(raw) is live


def test_status_round_trip_and_missing_status_resumes_at_pr(tmp_path):
    s = new_status("Chowder number", "2026-10-18")
    assert s.spec == "docs/superpowers/specs/2026-10-18-chowder-number-design.md"
    assert s.plan == "docs/superpowers/plans/2026-10-18-chowder-number.md"
    write_status(tmp_path / "s.json", s)
    assert read_status(tmp_path / "s.json") == s
    assert resume_stage(read_status(tmp_path / "none.json")) == "pr"


def test_resume_stage_is_the_saved_stage():
    assert resume_stage(Status("a", "Row A", "build", "s", "p")) == "build"


@pytest.mark.parametrize(
    ("stage", "outcome", "nxt"),
    [
        ("spec", "ok", "plan"),
        ("plan", "ok", "build"),
        ("build", "more", "build"),
        ("build", "ok", "pr"),
        ("pr", "ok", "done"),
        ("plan", "park", "parked"),
    ],
)
def test_next_stage(stage, outcome, nxt):
    assert next_stage(stage, outcome) == nxt


def test_has_calls_section():
    good = "## Calls made for the owner\n\n- Band 8-12. Rejected: 10-15.\n- Flag only. Rejected: score input.\n\n## Next"
    assert has_calls_section(good)
    assert not has_calls_section(good.replace("Rejected: score input", "score input"))
    assert not has_calls_section("## Goals\n- x. Rejected: y")
    assert not has_calls_section("## Calls made for the owner\n\n## Next")


def test_owner_questions_reads_bullets_until_the_next_section():
    text = "## Calls made for the owner\n- a Rejected: b\n\n## Questions for the owner\n- Include REITs? Recommended: no\n- Cap? Recommended: 6%\n\n## Plan\n- not a question\n"
    assert owner_questions(text) == ["Include REITs? Recommended: no", "Cap? Recommended: 6%"]
    assert owner_questions("## Questions for the owner\n\n## Next\n") == []


def test_owner_questions_is_empty_without_the_heading():
    assert owner_questions("## Calls made for the owner\n- a Rejected: b\n") == []


def test_owner_questions_collapses_inner_whitespace_to_single_spaces():
    assert owner_questions("## Questions for the owner\n-   Cap?\tRecommended:   6%  \n") == ["Cap? Recommended: 6%"]
