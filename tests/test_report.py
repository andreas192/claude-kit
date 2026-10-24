"""UNIT: kit.bench.report, the markdown table of measures per window."""

from builders import session

from kit.bench.benchmarks import Benchmark
from kit.bench.report import MIN_SESSIONS, Column, report_lines

FIXED_MEASURE = Benchmark("BX", "session count", "any", lambda sessions: float(len(sessions)))
NAN_MEASURE = Benchmark("BN", "nothing", "any", lambda sessions: float("nan"))


def sessions(n):
    return [session() for _ in range(n)]


def row(lines, key):
    return next(line for line in lines if line.startswith(f"| {key} "))


def test_min_sessions_constant():
    assert MIN_SESSIONS == 5


def test_delta_needs_min_sessions_on_both_sides():
    lines = report_lines([Column("pre-kit", sessions(6)), Column("v0.1.0", sessions(4))], None, [FIXED_MEASURE], [], 5)
    assert "not enough data" in row(lines, FIXED_MEASURE.key)


def test_control_delta_column_and_not_measured():
    cols = [Column("pre-kit", sessions(5)), Column("v0.1.0", sessions(5))]
    lines = report_lines(cols, cols, [FIXED_MEASURE], ["permission prompts: x"], 5)
    assert "control Δ pre-kit→v0.1.0" in lines[0] and lines[-1] == "- permission prompts: x"
    assert "Not measured:" in lines
    cells = [c.strip() for c in row(lines, FIXED_MEASURE.key).strip("|").split("|")]
    assert cells == ["BX session count", "5.00", "5.00", "0.00", "0.00", "any"]


def test_layout_without_control_and_sessions_row():
    lines = report_lines([Column("pre-kit", sessions(6)), Column("v0.1.0", sessions(9))], None, [FIXED_MEASURE], [])
    assert lines[0] == "| measure | pre-kit | v0.1.0 | Δ pre-kit→v0.1.0 | target |"
    assert lines[1].startswith("| ---")
    assert [c.strip() for c in lines[2].strip("|").split("|")][:3] == ["sessions", "6", "9"]
    assert [c.strip() for c in lines[3].strip("|").split("|")] == ["BX session count", "6.00", "9.00", "3.00", "any"]


def test_control_delta_uses_the_controls_own_counts():
    cols = [Column("pre-kit", sessions(6)), Column("v0.1.0", sessions(6))]
    control = [Column("pre-kit", sessions(6)), Column("v0.1.0", sessions(2))]
    cells = [c.strip() for c in row(report_lines(cols, control, [FIXED_MEASURE], []), FIXED_MEASURE.key).strip("|").split("|")]
    assert cells[3] == "0.00" and cells[4] == "not enough data"


def test_nan_delta_renders_as_fmt_renders_nan():
    lines = report_lines([Column("a", sessions(5)), Column("b", sessions(5))], None, [NAN_MEASURE], [])
    assert [c.strip() for c in row(lines, NAN_MEASURE.key).strip("|").split("|")] == ["BN nothing", "-", "-", "-", "any"]


def test_no_not_measured_section_when_empty():
    assert "Not measured:" not in report_lines([Column("a", sessions(5)), Column("b", sessions(5))], None, [FIXED_MEASURE], [])


def test_q4_row_from_fix_share_with_delta_and_not_enough_data():
    cols = [Column("pre-kit", sessions(6), 0.5), Column("v0.1.0", sessions(6), 0.25)]
    cells = [c.strip() for c in row(report_lines(cols, None, [], []), "Q4").strip("|").split("|")]
    assert cells == ["Q4 share of merges followed by a fix within 7 days", "0.50", "0.25", "-0.25", "falls"]
    thin = [Column("pre-kit", sessions(6), 0.5), Column("v0.1.0", sessions(2), 0.25)]
    assert "not enough data" in row(report_lines(thin, None, [], []), "Q4")


def test_q4_control_delta_uses_the_controls_fix_share():
    cols = [Column("pre-kit", sessions(6), 0.5), Column("v0.1.0", sessions(6), 0.25)]
    control = [Column("pre-kit", sessions(6), 0.2), Column("v0.1.0", sessions(6), 0.3)]
    cells = [c.strip() for c in row(report_lines(cols, control, [], []), "Q4").strip("|").split("|")]
    assert cells[3:5] == ["-0.25", "0.10"]


def test_q4_nan_when_no_merges():
    lines = report_lines([Column("a", sessions(5)), Column("b", sessions(5))], None, [], [])
    assert [c.strip() for c in row(lines, "Q4").strip("|").split("|")][1:4] == ["-", "-", "-"]
