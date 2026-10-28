"""UNIT: kit.roadmap, the docs/roadmap.md parser and validator."""

import pytest
from builders import GOOD

from kit.errors import KitError
from kit.roadmap import RoadmapError, item_key, parse_roadmap, read_roadmap, requester_roadmaps


def test_parse_keeps_file_order_sections_and_fields():
    r = parse_roadmap(GOOD)
    assert [i.status for i in r.items] == ["open", "open", "owner", "done"]
    v = r.items[1]
    assert (v.section, v.depends_on, v.key) == (
        "Features",
        ("Two-stage dividend discount model",),
        "valuation-against-the-company-s-own-history",
    )
    assert r.items[2].blocked_by == "whether to recreate the cluster" and r.items[3].section == "Known data bugs"


@pytest.mark.parametrize(
    "title, branch_key",
    [
        (
            "Automatic classification of one-off dividend schedule shifts (a short year whose gaps between payments are all normal), so Data fixes needs fewer manual settlements",
            "automatic-classification-of-one-off-dividend",
        ),
        ("Regime or beta as a scoring input (option 3 of 2026-10-14)", "regime-or-beta-as-a-scoring-input-option-3-of-2026"),
        (
            "Holdings and income projection (yield on cost, concentration, forward income)",
            "holdings-and-income-projection-yield-on-cost",
        ),
    ],
)
def test_item_key_matches_the_existing_loop_branches(title, branch_key):
    assert item_key(title) == branch_key


def test_crlf_and_trailing_spaces_are_tolerated():
    assert parse_roadmap(GOOD.replace("\n", "\r\n").replace("Status: open", "Status: open  ")).items[0].status == "open"


@pytest.mark.parametrize(
    "fields, message",
    [
        ("", "missing Status"),
        ("- Status: later", "unknown Status 'later'"),
        ("- Status: blocked", "Blocked by is required when Status is blocked"),
        ("- Status: open\n- Blocked by: x", "Blocked by is only for owner or blocked"),
        ("- Status: open\n- Owner: me", "unknown field 'Owner'"),
        ("- Status: open\n- Depends on: Nowhere", "Depends on 'Nowhere' is not an item"),
    ],
)
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


def test_error_text_is_one_path_line_message_per_problem():
    with pytest.raises(RoadmapError) as e:
        parse_roadmap("### A\n\n### B\n- Status: x\n")
    assert str(e.value).splitlines() == [
        "docs/roadmap.md:1: missing Status",
        "docs/roadmap.md:3: unknown Status 'x'",
    ]


def test_by_title_finds_an_item_and_refuses_an_unknown_one():
    r = parse_roadmap(GOOD)
    assert r.by_title("Host port for the UI").status == "owner"
    with pytest.raises(KitError, match="Nowhere"):
        r.by_title("Nowhere")


def test_read_roadmap_reads_the_repo_file_and_names_a_missing_one(tmp_path):
    with pytest.raises(KitError, match="roadmap.md not found"):
        read_roadmap(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "roadmap.md").write_text(GOOD)
    assert len(read_roadmap(tmp_path).items) == 4


def test_requested_by_is_a_field_on_any_status():
    text = "### A\n- Status: owner\n- Blocked by: review\n- Requested by: dividend-growth\n\n### B\n- Status: done\n- Requested by: investment\n"
    roadmap = parse_roadmap(text)
    assert [i.requested_by for i in roadmap.items] == ["dividend-growth", "investment"]


def test_requested_by_is_blank_when_absent():
    assert parse_roadmap("### A\n- Status: open\n").items[0].requested_by == ""


def _requested(*names: str) -> str:
    return "".join(f"### {n}\n- Status: done\n- Requested by: {n}\n\n" for n in names)


def test_requester_roadmaps_reads_siblings(tmp_path):
    (tmp_path / "dg" / "docs").mkdir(parents=True)
    (tmp_path / "dg" / "docs" / "roadmap.md").write_text("### Fix\n- Status: done\n")
    text = "### Fix\n- Status: done\n- Requested by: dg\n\n### X\n- Status: done\n- Requested by: gone\n"
    found = requester_roadmaps(tmp_path / "inv", parse_roadmap(text))
    assert found["dg"].by_title("Fix").status == "done" and found["gone"] is None


def test_requester_roadmaps_maps_invalid_and_unreadable_files_to_none(tmp_path):
    (tmp_path / "bad" / "docs").mkdir(parents=True)
    (tmp_path / "bad" / "docs" / "roadmap.md").write_text("### Fix\n- Status: nope\n")
    (tmp_path / "bin" / "docs").mkdir(parents=True)
    (tmp_path / "bin" / "docs" / "roadmap.md").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "dir" / "docs" / "roadmap.md").mkdir(parents=True)
    found = requester_roadmaps(tmp_path / "inv", parse_roadmap(_requested("bad", "bin", "dir")))
    assert found == {"bad": None, "bin": None, "dir": None}


def test_requester_roadmaps_covers_only_done_requested_items(tmp_path):
    text = "### A\n- Status: open\n- Requested by: a\n\n### B\n- Status: done\n\n### C\n- Status: done\n- Requested by: c\n"
    assert set(requester_roadmaps(tmp_path / "inv", parse_roadmap(text))) == {"c"}
