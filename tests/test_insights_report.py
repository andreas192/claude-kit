"""UNIT: kit.insights.report."""

from builders import session

from kit.bench.report import Column
from kit.insights.findings import Finding, Week
from kit.insights.loopstats import STAGES, LoopStats
from kit.insights.report import NO_LOOP, NO_SESSIONS, finding_lines, loop_table, loop_value, repo_section, report_text

EMPTY = LoopStats(0, 0, 0, 0, 0, 0, 0, 0, dict.fromkeys(STAGES, 0.0), float("nan"))
BUSY = LoopStats(2, 5, 1, 0, 2, 0, 0, 0, dict.fromkeys(STAGES, 0.5), 60.0)


def test_loop_values_are_formatted_per_kind():
    assert loop_value(BUSY, "usd:spec") == "0.50"
    assert loop_value(BUSY, "total_usd") == "2.50"
    assert loop_value(BUSY, "opus_share") == "40%"
    assert loop_value(EMPTY, "usd_per_shipped") == "-"
    assert loop_value(BUSY, "shipped") == "1"


def test_loop_table_has_a_column_per_group():
    lines = loop_table([("W1", EMPTY), ("W2", BUSY)])
    assert lines[0] == "| loop | W1 | W2 |"
    assert "| $ total | 0.00 | 2.50 |" in lines


def test_section_says_so_when_there_is_no_loop_and_no_sessions():
    text = "\n".join(repo_section("repo", [Week("W1", EMPTY, [], ())], [], [Column("pre-kit", [])], []))
    assert text.count(NO_LOOP) == 2 and NO_SESSIONS in text
    assert "No rule fired" in text


def test_section_skips_weeks_without_sessions():
    weeks = [Week("W1", BUSY, [], ()), Week("W2", BUSY, [session(peak=1000)], ())]
    text = "\n".join(repo_section("repo", weeks, [("v0.3.0", BUSY)], [], []))
    session_head = next(line for line in text.splitlines() if line.startswith("| measure"))
    assert "W1" not in session_head and "W2" in session_head
    assert "| loop | v0.3.0 |" in text


def test_findings_and_advice_render():
    assert finding_lines([Finding("L2", "4 builds", "smaller tasks")]) == ["- **L2** 4 builds. smaller tasks."]
    text = report_text("2026-W43", [["## a", ""]], ["- change x"])
    assert text.startswith("# kit insights: 2026-W43") and "## Suggested changes\n\n- change x" in text
    assert "Suggested changes" not in report_text("t", [], [])
