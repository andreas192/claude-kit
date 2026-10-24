"""UNIT: kit.loop.prs, the loop PR list and the park note carried in a draft PR body."""

import json

from kit.loop.prs import ParkNote, Pr, loop_prs, park_body, parse_park_body

ATTRIBUTION = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


def test_loop_prs_keeps_loop_heads_sorted():
    raw = json.dumps(
        [
            {"number": 7, "headRefName": "loop/b", "state": "CLOSED", "createdAt": "2026-10-18", "url": "u7"},
            {"number": 5, "headRefName": "feat/x", "state": "OPEN", "createdAt": "2026-10-17", "url": "u5"},
            {
                "number": 6,
                "headRefName": "loop/a",
                "state": "OPEN",
                "createdAt": "2026-10-17",
                "url": "u6",
                "isDraft": True,
                "body": "Parked: x",
            },
        ]
    )
    prs = loop_prs(raw)
    assert [p.number for p in prs] == [6, 7]
    assert (prs[0].is_draft, prs[0].body, prs[1].is_draft, prs[1].body) == (True, "Parked: x", False, "")


def test_park_body_round_trips_with_questions():
    body = park_body("owner questions", "s.md", "p.md", ["Include REITs? Recommended: no"])
    assert parse_park_body(body) == ParkNote("owner questions", ("Include REITs? Recommended: no",))
    assert body.rstrip().endswith(ATTRIBUTION)


def test_park_body_leaves_out_empty_spec_plan_and_questions():
    body = park_body("tests red", "", "", [])
    assert body == f"Parked: tests red\n\n{ATTRIBUTION}\n"
    assert parse_park_body(body) == ParkNote("tests red", ())


def test_park_body_lists_spec_and_plan_and_every_question():
    body = park_body("owner questions", "s.md", "p.md", ["a?", "b?"])
    assert "Spec: s.md" in body and "Plan: p.md" in body
    assert parse_park_body(body).questions == ("a?", "b?")


def test_parse_park_body_of_a_body_that_is_not_a_park_note_is_empty():
    assert parse_park_body("Implements the thing.") == ParkNote("", ())


def test_pr_defaults():
    pr = Pr(1, "loop/a", "OPEN", "2026-10-17", "u")
    assert (pr.title, pr.is_draft, pr.body) == ("", False, "")
