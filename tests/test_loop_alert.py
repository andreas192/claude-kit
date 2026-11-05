"""UNIT: kit.loop.alert, the record of a failing probe in the runtime dir."""

from datetime import datetime

from kit.loop.alert import clear_probe_failure, probe_failure_line, record_probe_failure

FIRST = datetime(2026, 11, 3, 15, 0, 5)
LATER = datetime(2026, 11, 4, 10, 0, 9)


def test_no_record_gives_no_line(tmp_path):
    assert probe_failure_line(tmp_path) == ""


def test_the_line_gives_the_first_failure_and_the_latest_reason(tmp_path):
    record_probe_failure(tmp_path, FIRST, "probe failed: expired")
    record_probe_failure(tmp_path, LATER, "probe gave no usage")
    assert probe_failure_line(tmp_path) == "loop probe failing since 2026-11-03T15:00:05: probe gave no usage"


def test_a_reason_over_several_lines_stays_on_one_line(tmp_path):
    record_probe_failure(tmp_path, FIRST, "probe failed:\n  expired\n")
    assert probe_failure_line(tmp_path) == "loop probe failing since 2026-11-03T15:00:05: probe failed: expired"


def test_the_record_creates_a_missing_runtime_dir(tmp_path):
    record_probe_failure(tmp_path / "new", FIRST, "why")
    assert probe_failure_line(tmp_path / "new") != ""


def test_clear_removes_the_record_and_is_safe_without_one(tmp_path):
    record_probe_failure(tmp_path, FIRST, "why")
    clear_probe_failure(tmp_path)
    clear_probe_failure(tmp_path)
    assert probe_failure_line(tmp_path) == ""
