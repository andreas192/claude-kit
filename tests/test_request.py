"""UNIT: kit.request, the pure logic of a cross-repo roadmap request."""

import pytest

from kit.errors import KitError
from kit.loop.driver import CO_AUTHOR
from kit.loop.prs import ATTRIBUTION
from kit.request import (
    RequestError,
    allowed_target,
    commit_message,
    existing_item,
    filed_item,
    parse_request,
    pr_body,
    pr_title,
    require_version,
    target_by_name,
    with_request,
)
from kit.roadmap import RoadmapError, parse_roadmap

REQ = "Target: investment\n### Fix FX rates\n- Status: open\n- Depends on: Other\n- Spec: docs/x.md\n\nRates are stale.\n"


def test_parse_request_reads_target_title_kept_fields_and_body():
    r = parse_request(REQ)
    assert (r.target, r.title, r.key) == ("investment", "Fix FX rates", "fix-fx-rates")
    assert r.fields == (("Spec", "docs/x.md"),) and r.body == "Rates are stale."


def test_parse_request_without_target_line():
    assert parse_request("### A\n\nbody\n").target == ""


def test_parse_request_skips_leading_blank_lines_before_target():
    r = parse_request("\n  \nTarget: investment\n\n### A\n")
    assert (r.target, r.title) == ("investment", "A")


@pytest.mark.parametrize(
    "text, message",
    [
        ("just text\n", "no ### item"),
        ("### A\n\n### B\n", "exactly one ### item"),
        ("## Section\n### A\n", "no ## section"),
        ("Target: investment\nplease fix\n### A\n", "text before the ### item"),
        ("Target: investment\n### !!!\n", "no letters or digits"),
        ("Target: investment\n### Øæ ß\n", "no letters or digits"),
    ],
)
def test_parse_request_rejects(text, message):
    with pytest.raises(RequestError, match=message):
        parse_request(text)


def test_filed_item_sets_owner_fields():
    assert filed_item(parse_request(REQ), "dividend-growth") == (
        "### Fix FX rates\n- Status: owner\n"
        "- Blocked by: the owner's review of a request from dividend-growth\n"
        "- Requested by: dividend-growth\n- Spec: docs/x.md\n\nRates are stale.\n"
    )


def test_filed_item_without_body_ends_after_the_fields():
    assert filed_item(parse_request("### A\n"), "dg").endswith("- Requested by: dg\n")


def test_with_request_creates_the_section_at_the_end():
    out = with_request("## Now\n\n### A\n- Status: open\n", "### B\n- Status: open\n")
    assert out.endswith("\n## Requests\n\n### B\n- Status: open\n")
    assert parse_roadmap(out).by_title("B").section == "Requests"


def test_with_request_appends_inside_an_existing_requests_section_that_is_not_last():
    text = "## Requests\n\n### A\n- Status: open\n\n## Later\n\n### C\n- Status: open\n"
    out = with_request(text, "### B\n- Status: open\n")
    assert parse_roadmap(out).by_title("B").section == "Requests"
    assert out.index("### B") < out.index("## Later")


def test_with_request_appends_to_a_requests_section_that_is_last():
    out = with_request("## Requests\n\n### A\n- Status: open\n", "### B\n- Status: open\n")
    assert out == "## Requests\n\n### A\n- Status: open\n\n### B\n- Status: open\n"


def test_with_request_that_does_not_validate_raises():
    with pytest.raises(RoadmapError, match="unknown field 'Colour'"):
        with_request("", "### B\n- Status: open\n- Colour: red\n")


def test_existing_item_matches_by_key():
    roadmap = parse_roadmap("## Now\n\n### Fix FX rates\n- Status: open\n")
    assert existing_item(roadmap, "fix-fx-rates").title == "Fix FX rates"
    assert existing_item(roadmap, "other") is None


def test_allowed_target_resolves_relative_to_repo(tmp_path):
    repo, inv = tmp_path / "dg", tmp_path / "investment"
    assert allowed_target(repo, ("../investment",), inv) == inv.resolve()
    with pytest.raises(KitError, match="not in requests.targets"):
        allowed_target(repo, ("../investment",), tmp_path / "capital-trading")


def test_target_by_name(tmp_path):
    assert target_by_name(tmp_path / "dg", ("../investment",), "investment") == (tmp_path / "investment").resolve()
    with pytest.raises(KitError, match="'capital-trading' is not in requests.targets"):
        target_by_name(tmp_path / "dg", ("../investment",), "capital-trading")
    with pytest.raises(KitError, match=r"^the request has no Target: line; add a first line `Target: <repo>`$"):
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


def test_pr_body_without_loop_branch_omits_the_loop_line():
    assert "loop" not in pr_body("### T\n", "dg", "").lower()
