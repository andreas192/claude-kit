"""UNIT: kit.loop.pick, the deterministic choice of the next roadmap item."""

import pytest
from builders import GOOD

from kit.loop.pick import Pick, none_note, pick
from kit.loop.prs import Pr, park_body
from kit.roadmap import parse_roadmap

FIRST = "loop/two-stage-dividend-discount-model"


@pytest.fixture
def roadmap():
    return parse_roadmap(GOOD)


def test_pick_is_the_first_open_item_not_taken_and_unblocked(roadmap):
    p = pick(roadmap, branches=[], prs=[])
    assert p.item.title == "Two-stage dividend discount model"
    assert [(s.item.title, s.reason) for s in p.skipped] == [
        (
            "Valuation against the company's own history",
            "depends on Two-stage dividend discount model (open)",
        )
    ]


def test_a_pr_in_any_state_or_a_bare_branch_takes_an_item(roadmap):
    pr = Pr(7, FIRST, "CLOSED", "2026-10-20", "https://x/pull/7")
    assert pick(roadmap, [], [pr]).skipped[0].reason == "taken by https://x/pull/7"
    assert pick(roadmap, [FIRST], []).skipped[0].reason == f"taken by branch {FIRST}"


def test_the_newest_pr_by_created_names_the_taker(roadmap):
    new = Pr(8, FIRST, "OPEN", "2026-10-22", "https://x/pull/8")
    old = Pr(7, FIRST, "CLOSED", "2026-10-20", "https://x/pull/7")
    assert pick(roadmap, [], [old, new]).skipped[0].reason == "taken by https://x/pull/8"


def test_a_done_dependency_does_not_skip_the_item(roadmap):
    r = parse_roadmap(GOOD.replace("### Two-stage dividend discount model\n- Status: open", "### Two-stage dividend discount model\n- Status: done"))
    assert pick(r, [], []).item.title == "Valuation against the company's own history"


def test_owner_blocked_and_active_items_are_never_picked():
    r = parse_roadmap("### A\n- Status: owner\n- Blocked by: me\n\n### B\n- Status: active\n")
    assert pick(r, [], []) == Pick(None, ())


def test_none_note_lists_owner_items_and_parked_drafts(roadmap):
    draft = Pr(9, "loop/x", "OPEN", "2026-10-21", "https://x/pull/9", is_draft=True, body=park_body("tests red", "", "", []))
    note = none_note(roadmap, [draft])
    assert "- Host port for the UI: whether to recreate the cluster" in note
    assert "- https://x/pull/9: tests red" in note
    assert "## Blocked" not in note


def test_none_note_lists_only_open_drafts_and_names_a_missing_reason_parked(roadmap):
    closed = Pr(8, "loop/y", "CLOSED", "2026-10-21", "https://x/pull/8", is_draft=True, body=park_body("old", "", "", []))
    bare = Pr(9, "loop/x", "OPEN", "2026-10-21", "https://x/pull/9", is_draft=True, body="hand-made draft")
    note = none_note(roadmap, [closed, bare])
    assert "pull/8" not in note
    assert "- https://x/pull/9: parked" in note


def test_none_note_leaves_out_empty_sections_and_ignores_non_draft_prs():
    r = parse_roadmap("### A\n- Status: blocked\n- Blocked by: a thing\n")
    merged = Pr(1, "loop/a", "MERGED", "2026-10-21", "u")
    note = none_note(r, [merged])
    assert "## Blocked\n\n- A: a thing" in note
    assert "Waiting on the owner" not in note and "Parked loop PRs" not in note
