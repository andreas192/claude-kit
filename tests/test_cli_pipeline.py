"""PIPELINE: the kit CLI end to end over temp git repos and a temp transcript root."""

import hashlib
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from builders import assistant, commit, git, rec, tag
from test_detect import DGI_WIRING, build_repo

from kit.bench.transcripts import transcript_dir_name
from kit import cli
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


def test_bench_dot_uses_the_sibling_kit_repo_as_control(bench_repo, monkeypatch, capsys):
    repo, root = bench_repo
    (repo.parent / "sibling").mkdir()
    write_kitfile(repo.parent / "sibling", KitFile("pytest", (Apply("v0.1.0", "x", APPLIED),)))
    monkeypatch.chdir(repo)
    assert main(["bench", ".", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# kit bench: repo (") and "control Δ pre-kit→v0.1.0" in out


def test_bench_with_a_bad_kit_json_in_the_target_is_exit_1(bench_repo, capsys):
    repo, root = bench_repo
    (repo / ".claude" / "kit.json").write_text("{oops")
    assert main(["bench", str(repo), "--root", str(root)]) == 1
    assert "invalid kit.json" in capsys.readouterr().err


def test_status_survives_a_corrupt_sibling(tmp_path, capsys):
    (tmp_path / "bad" / ".claude").mkdir(parents=True)
    (tmp_path / "bad" / ".claude" / "kit.json").write_text("{oops")
    assert main(["status", "--base", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "bad  invalid kit.json"


KIT_SOURCE = Path(__file__).parents[1]
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
LOCAL_HOOKS = (".claude/hooks/test-layer-guard.mjs", ".claude/hooks/context-warn.mjs")
BRANCH = "chore/claude-kit-v0.1.0"


def hook_entry(script: str) -> dict:
    return {"hooks": [{"type": "command", "command": f"node .claude/hooks/{script}"}]}


@pytest.fixture
def kit_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "kit-repo"
    for folder in ("plugin", "starter"):
        shutil.copytree(KIT_SOURCE / folder, repo / folder)
    git(repo, "init", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "release")
    tag(repo, "v0.1.0")
    monkeypatch.setattr(cli, "KIT_REPO", repo)
    return repo


@pytest.fixture
def target(tmp_path: Path) -> Path:
    (tmp_path / "target").mkdir()
    repo = build_repo(tmp_path / "target", "dgi", DGI_WIRING, "run_refresh")
    (repo / ".claude/hooks/context-warn.mjs").write_text("// stock context-warn\n")
    settings = {"hooks": {"PreToolUse": [hook_entry("test-layer-guard.mjs")], "Stop": [hook_entry("context-warn.mjs")]}}
    (repo / ".claude/settings.json").write_text(json.dumps(settings))
    git(repo, "init", "-b", "main")
    for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        git(repo, "config", key, value)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "initial")
    return repo


def apply_args(tmp_path: Path, target: Path, version: str = "v0.1.0") -> list[str]:
    known = {name: [hashlib.sha256((target / name).read_bytes()).hexdigest()] for name in LOCAL_HOOKS if (target / name).exists()}
    known_file = tmp_path / "known.json"
    known_file.write_text(json.dumps(known))
    return [
        "apply", str(target), "--version", version, "--test-command", "true", "--no-pr",
        "--kit-home", str(tmp_path / "kit-home"), "--root", str(tmp_path / "projects"),
        "--known-hashes", str(known_file),
    ]


def commits(repo: Path) -> int:
    return int(subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=repo, capture_output=True, text=True).stdout)


@needs_node
def test_apply_puts_the_version_into_the_repo_on_a_branch(tmp_path, target, kit_repo):
    argv = apply_args(tmp_path, target)
    before = commits(target)
    assert main(argv) == 0
    assert subprocess.run(["git", "branch", "--show-current"], cwd=target, capture_output=True, text=True).stdout.strip() == BRANCH
    applies = json.loads((target / ".claude/kit.json").read_text())["applies"]
    assert [a["version"] for a in applies] == ["v0.1.0"] and len(applies[0]["commit"]) == 40
    settings = json.loads((target / ".claude/settings.json").read_text())
    assert "kit@kit-v0-1-0" in settings["enabledPlugins"]
    assert "test-layer-guard.mjs" not in json.dumps(settings.get("hooks", {})) and "context-warn.mjs" not in json.dumps(settings.get("hooks", {}))
    assert json.loads((target / ".claude/kit.json").read_text())["test_command"] == "true"
    assert not any((target / name).exists() for name in LOCAL_HOOKS)
    assert (target / ".claude/kit-bench/baseline.json").is_file()
    assert (target / "docs/token-strategy.md").is_file() and (target / ".claude/test-layers.json").is_file()
    assert commits(target) == before + 2
    assert subprocess.run(["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True).stdout == ""
    assert sorted(p.name for p in (tmp_path / "kit-home").iterdir()) == ["v0.1.0"]


@needs_node
def test_apply_twice_stops_with_already_on_and_adds_no_commit(tmp_path, target, kit_repo, capsys):
    argv = apply_args(tmp_path, target)
    assert main(argv) == 0
    count = commits(target)
    assert main(argv) == 1
    assert "error: already on v0.1.0" in capsys.readouterr().err
    assert commits(target) == count


@needs_node
def test_apply_a_newer_version_replaces_the_marketplace_entry(tmp_path, target, kit_repo):
    assert main(apply_args(tmp_path, target)) == 0
    manifest = kit_repo / "plugin/.claude-plugin/plugin.json"
    manifest.write_text(manifest.read_text().replace("0.1.0", "0.1.1"))
    git(kit_repo, "commit", "-am", "release 0.1.1")
    tag(kit_repo, "v0.1.1")
    assert main(apply_args(tmp_path, target, "v0.1.1")) == 0
    settings = json.loads((target / ".claude/settings.json").read_text())
    assert list(settings["extraKnownMarketplaces"]) == ["kit-v0-1-1"] and list(settings["enabledPlugins"]) == ["kit@kit-v0-1-1"]
    assert [a["version"] for a in json.loads((target / ".claude/kit.json").read_text())["applies"]] == ["v0.1.0", "v0.1.1"]


@needs_node
def test_apply_with_a_failing_test_command_leaves_the_branch_and_records_nothing(tmp_path, target, kit_repo, capsys):
    argv = apply_args(tmp_path, target)
    argv[argv.index("--test-command") + 1] = "false"
    assert main(argv) == 1
    err = capsys.readouterr().err
    assert "tests: false failed; this may predate the kit" in err
    assert "branch chore/claude-kit-v0.1.0 left for inspection; no PR" in err
    assert subprocess.run(["git", "branch", "--show-current"], cwd=target, capture_output=True, text=True).stdout.strip() == BRANCH
    assert not (target / ".claude/kit.json").exists()
    assert commits(target) == 1


def test_apply_on_a_dirty_repo_stops_before_any_change(tmp_path, target, kit_repo, capsys):
    (target / "scratch.txt").write_text("wip")
    assert main(apply_args(tmp_path, target)) == 1
    assert "error: uncommitted changes" in capsys.readouterr().err
    assert not (tmp_path / "kit-home").exists()
