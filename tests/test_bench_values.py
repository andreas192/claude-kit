"""UNIT: kit.bench.run.baseline_values and write_baseline."""

import json

from builders import commit, git, session

from kit.bench.run import baseline_values, write_baseline
from kit.gitrun import run

KEYS = [f"B{i}" for i in range(1, 14)] + ["F1", "F2", "F3", "Q1", "Q2", "Q3", "S1", "S2"]


def test_baseline_values_have_every_benchmark_and_measure_key():
    assert list(baseline_values([session(peak=50_000), session(peak=70_000)])) == KEYS


def test_nan_measure_serializes_as_null():
    values = baseline_values([session()])
    assert values["Q1"] is None  # no reviewers: nothing to measure
    assert json.loads(json.dumps(values))["Q1"] is None


def test_measured_values_stay_numbers():
    assert baseline_values([session(peak=50_000), session(peak=70_000)])["B1"] == 60.0


def test_write_baseline_writes_json_with_q4_into_the_repo(tmp_path):
    repo, root = tmp_path / "repo", tmp_path / "projects"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    commit(repo, {"a.py": "1"}, "feat a", "2026-10-01T10:00:00Z")
    commit(repo, {"a.py": "2"}, "fix a", "2026-10-02T10:00:00Z")
    path = write_baseline(repo, root, run)
    assert path == repo / ".claude" / "kit-bench" / "baseline.json"
    data = json.loads(path.read_text())
    assert data["Q4"] == 0.5 and data["Q1"] is None and list(data)[:2] == ["B1", "B2"]
