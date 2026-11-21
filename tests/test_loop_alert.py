"""UNIT: kit.loop.alert, the probe and env-failure records in the runtime dir."""

from datetime import datetime

from kit.loop.alert import (
    ENV_FAILURE_FILE,
    alert_lines,
    clear_env_failure,
    clear_probe_failure,
    env_failure_line,
    probe_failure_line,
    record_env_failure,
    record_probe_failure,
)

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


def test_no_env_record_is_no_line(tmp_path):
    assert env_failure_line(tmp_path) == ""

def test_env_record_keeps_the_first_time_and_the_latest_reason(tmp_path):
    record_env_failure(tmp_path, FIRST, "roadmap: docs/roadmap.md:71: Blocked by is only for owner or blocked")
    record_env_failure(tmp_path, LATER, "git fetch origin failed (exit 1)")
    assert env_failure_line(tmp_path) == "loop stopped since 2026-11-03T15:00:05: git fetch origin failed (exit 1)"

def test_env_record_reason_is_one_line(tmp_path):
    record_env_failure(tmp_path, FIRST, "spec stage:\n  session failed\n")
    assert env_failure_line(tmp_path).endswith(": spec stage: session failed")

def test_env_record_creates_a_missing_runtime_dir(tmp_path):
    record_env_failure(tmp_path / "new", FIRST, "why")
    assert env_failure_line(tmp_path / "new") != ""

def test_env_clear_is_idempotent(tmp_path):
    record_env_failure(tmp_path, FIRST, "why")
    clear_env_failure(tmp_path)
    clear_env_failure(tmp_path)
    assert env_failure_line(tmp_path) == ""

def test_a_blank_record_file_reads_as_no_record(tmp_path):
    (tmp_path / ENV_FAILURE_FILE).write_text("  \n")
    assert env_failure_line(tmp_path) == "" and alert_lines(tmp_path) == []

def test_alert_lines_put_the_probe_before_the_env_stop_and_skip_absent_ones(tmp_path):
    assert alert_lines(tmp_path) == []
    record_env_failure(tmp_path, FIRST, "env why")
    assert alert_lines(tmp_path) == ["loop stopped since 2026-11-03T15:00:05: env why"]
    record_probe_failure(tmp_path, FIRST, "probe why")
    assert alert_lines(tmp_path) == [
        "loop probe failing since 2026-11-03T15:00:05: probe why",
        "loop stopped since 2026-11-03T15:00:05: env why",
    ]
