"""PIPELINE: the kit CLI end to end over temp git repos and a temp transcript root."""

from datetime import date
from pathlib import Path

import pytest
from builders import assistant, commit, git, rec

from kit.bench.transcripts import transcript_dir_name
from kit.cli import main
from kit.kitfile import Apply, KitFile, write_kitfile

APPLIED = "2026-10-18T00:00:00Z"


def write_session(root: Path, repo: Path, name: str, start: str, peak: int) -> None:
    directory = root / transcript_dir_name(repo)
    directory.mkdir(parents=True, exist_ok=True)
    lines = [rec(start), assistant("m1", read=peak)]
    (directory / f"{name}.jsonl").write_text("\n".join(lines) + "\n")


@pytest.fixture
def bench_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo, root = tmp_path / "repo", tmp_path / "projects"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    commit(repo, {"a.py": "1"}, "feat a", "2026-10-10T10:00:00Z")
    write_kitfile(repo, KitFile("pytest", (Apply("v0.1.0", "abc", APPLIED),)))
    commit(repo, {".claude/kit.json": (repo / ".claude/kit.json").read_text()}, "apply kit", APPLIED)
    for i in range(6):
        write_session(root, repo, f"pre{i}", f"2026-10-1{i}T09:00:00Z", 50_000)
    for i in range(5):
        write_session(root, repo, f"post{i}", f"2026-10-2{i}T09:00:00Z", 30_000)
    return repo, root


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip("|").split("|")]


def test_bench_prints_both_columns_and_writes_the_dated_report(bench_repo, capsys):
    repo, root = bench_repo
    assert main(["bench", str(repo), "--root", str(root)]) == 0
    out = capsys.readouterr().out
    header = cells(next(line for line in out.splitlines() if line.startswith("| measure")))
    assert "pre-kit" in header and "v0.1.0" in header
    b1 = cells(next(line for line in out.splitlines() if line.startswith("| B1 ")))
    assert float(b1[3].replace(",", "")) == -20.0
    assert (repo / ".claude" / "kit-bench" / f"{date.today()}.md").is_file()


def test_bench_twice_leaves_the_same_report(bench_repo, capsys):
    repo, root = bench_repo
    report = repo / ".claude" / "kit-bench" / f"{date.today()}.md"
    assert main(["bench", str(repo), "--root", str(root)]) == 0
    first = report.read_text()
    assert main(["bench", str(repo), "--root", str(root)]) == 0
    assert report.read_text() == first


def test_bench_without_kit_json_has_one_pre_kit_column(tmp_path, capsys):
    repo, root = tmp_path / "plain", tmp_path / "projects"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    write_session(root, repo, "s", "2026-10-10T09:00:00Z", 50_000)
    assert main(["bench", str(repo), "--root", str(root)]) == 0
    header = cells(next(line for line in capsys.readouterr().out.splitlines() if line.startswith("| measure")))
    assert header == ["measure", "pre-kit", "target"]


def test_bench_since_drops_earlier_sessions(bench_repo, capsys):
    repo, root = bench_repo
    assert main(["bench", str(repo), "--root", str(root), "--since", "2026-10-20T00:00:00Z"]) == 0
    sessions = cells(next(line for line in capsys.readouterr().out.splitlines() if line.startswith("| sessions")))
    assert sessions[1:3] == ["0", "5"]


def test_bench_with_explicit_control_adds_control_delta(bench_repo, tmp_path, capsys):
    repo, root = bench_repo
    control = tmp_path / "other"
    control.mkdir()
    assert main(["bench", str(repo), "--control", str(control), "--root", str(root)]) == 0
    assert "control Δ pre-kit→v0.1.0" in capsys.readouterr().out


def test_bench_missing_repo_is_exit_1_with_error(tmp_path, capsys):
    assert main(["bench", str(tmp_path / "missing"), "--root", str(tmp_path)]) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_bench_missing_control_is_exit_1_with_error(bench_repo, tmp_path, capsys):
    repo, root = bench_repo
    assert main(["bench", str(repo), "--control", str(tmp_path / "missing"), "--root", str(root)]) == 1
    assert "control repo not found" in capsys.readouterr().err


def test_status_lists_kit_repos_under_base(tmp_path, capsys):
    (tmp_path / "a").mkdir()
    write_kitfile(tmp_path / "a", KitFile("pytest", (Apply("v0.2.0", "c", "t", (".claude/agents/x.md",)),)))
    assert main(["status", "--base", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "a  v0.2.0  overrides: .claude/agents/x.md"
