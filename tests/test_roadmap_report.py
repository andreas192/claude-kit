"""UNIT: kit.roadmap_report, the text `kit roadmap` prints: counts, titles, reasons and questions only."""

from builders import GOOD

from kit.loop.pick import Pick, Skip
from kit.loop.prs import Pr, park_body
from kit.roadmap import parse_roadmap
from kit.roadmap_report import format_report

ROADMAP = parse_roadmap(GOOD)


def draft(url: str, body: str, state: str = "OPEN", is_draft: bool = True) -> Pr:
    return Pr(1, "loop/x", state, "2026-10-17T10:00", url, "t", is_draft, body)


def test_every_section_is_present_in_order():
    first, second = ROADMAP.items[0], ROADMAP.items[1]
    result = Pick(first, (Skip(second, "depends on Two-stage dividend discount model (open)"),))
    prs = [draft("https://x/pull/7", park_body("owner questions", "s.md", "", ["Which basis?", "Which tax rate?"]))]
    lines = format_report(ROADMAP, result, prs).splitlines()
    assert lines == [
        "Items: 2 open, 1 owner, 0 blocked, 0 active, 1 done, 0 dropped",
        "Next pick: Two-stage dividend discount model",
        "Skipped:",
        "- Valuation against the company's own history: depends on Two-stage dividend discount model (open)",
        "For you this weekend:",
        "- Host port for the UI: whether to recreate the cluster",
        "- https://x/pull/7: owner questions",
        "    - Which basis?",
        "    - Which tax rate?",
    ]


def test_no_pick_prints_none_and_omits_empty_sections():
    done = parse_roadmap("### A\n- Status: done\n")
    assert format_report(done, Pick(None, ()), []).splitlines() == [
        "Items: 0 open, 0 owner, 0 blocked, 0 active, 1 done, 0 dropped",
        "Next pick: none",
    ]


def test_gh_error_keeps_the_counts_and_marks_the_pick_unknown():
    lines = format_report(ROADMAP, None, None, "not found").splitlines()
    assert lines[0] == "Items: 2 open, 1 owner, 0 blocked, 0 active, 1 done, 0 dropped"
    assert lines[1] == "Next pick: unknown (gh: not found)"
    assert "- Host port for the UI: whether to recreate the cluster" in lines
    assert lines[-1] == "- parked PRs: unknown (gh: not found)"


def test_only_open_drafts_count_as_parked():
    prs = [
        draft("https://x/pull/1", park_body("a", "", "", [])),
        draft("https://x/pull/2", park_body("b", "", "", []), state="CLOSED"),
        draft("https://x/pull/3", park_body("c", "", "", []), is_draft=False),
    ]
    out = format_report(ROADMAP, Pick(None, ()), prs)
    assert "- https://x/pull/1: a" in out
    assert "pull/2" not in out and "pull/3" not in out


DONE = parse_roadmap("### Fix\n- Status: done\n- Requested by: dg\n\n### Other\n- Status: done\n")


def test_weekend_lists_done_requests_the_requester_has_not_marked_done():
    requester = parse_roadmap("### Fix\n- Status: owner\n- Blocked by: waiting\n")
    text = format_report(DONE, None, [], requesters={"dg": requester})
    assert "- Tell dg: Fix is done" in text and "Other" not in text.split("For you this weekend:")[1]


def test_a_requester_with_the_item_done_clears_it():
    text = format_report(DONE, None, [], requesters={"dg": parse_roadmap("### Fix\n- Status: done\n")})
    assert "Tell dg" not in text


def test_an_unreadable_requester_roadmap_is_named():
    text = format_report(DONE, None, [], requesters={"dg": None})
    assert "- Tell dg: Fix is done (requester roadmap not found)" in text


def test_a_requester_roadmap_without_the_item_lists_it():
    text = format_report(DONE, None, [], requesters={"dg": parse_roadmap("### Else\n- Status: done\n")})
    assert "- Tell dg: Fix is done" in text and "not found" not in text


def test_requesters_default_to_no_tell_lines():
    assert "Tell" not in format_report(DONE, None, [])
