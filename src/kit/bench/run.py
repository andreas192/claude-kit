"""Wiring for `kit bench`: sessions + git history -> windows -> report file, and the baseline snapshot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from kit.bench.benchmarks import BENCHMARKS
from kit.bench.gitlog import default_branch, followed_by_fix, history, merged_at
from kit.bench.measures import MEASURES, NOT_MEASURED
from kit.bench.report import Column, report_lines
from kit.bench.transcripts import Session, load_sessions, main_checkout, project_dirs
from kit.bench.windows import PRE_KIT, Window, assign, drop_before, fix_share, make_windows
from kit.gitrun import Runner, require_dir
from kit.kitfile import KitFile, read_kitfile
from kit.status import find_kit_repos

BENCH_DIR = Path(".claude") / "kit-bench"
BASELINE = "baseline.json"
EVERYTHING = Window(PRE_KIT, "", "")


def default_control(repo: Path) -> Path | None:
    others = [r for r in find_kit_repos(repo.parent) if r.name != repo.name]
    return repo.parent / others[0].name if others else None


def nan_to_none(value: float) -> float | None:
    return None if value != value else value


def baseline_values(sessions: list[Session]) -> dict[str, float | None]:
    return {m.key: nan_to_none(m.measure(sessions)) for m in [*BENCHMARKS, *MEASURES]}


def repo_sessions(repo: Path, root: Path, test_command: str) -> list[Session]:
    dirs = project_dirs(root, main_checkout(repo))
    return [s for d in dirs for s in load_sessions(d, test_command)]


def repo_windows(repo: Path, kit: KitFile, run: Runner) -> list[Window]:
    branch = default_branch(repo, run)
    return make_windows([(a.version, merged_at(repo, a.version, branch, run) or a.applied_at) for a in kit.applies])


def repo_columns(repo: Path, windows: list[Window], root: Path, since: str, run: Runner) -> list[Column]:
    kit = read_kitfile(repo) or KitFile("", ())
    grouped = assign(drop_before(repo_sessions(repo, root, kit.test_command), since), windows)
    ms = history(repo, run)
    flags = followed_by_fix(ms)
    return [Column(w.name, grouped[w.name], fix_share(w, ms, flags)) for w in windows]


def write_baseline(repo: Path, root: Path, run: Runner) -> Path:
    kit = read_kitfile(repo) or KitFile("", ())
    ms = history(repo, run)
    values = {**baseline_values(repo_sessions(repo, root, kit.test_command)), "Q4": nan_to_none(fix_share(EVERYTHING, ms, followed_by_fix(ms)))}
    path = repo / BENCH_DIR / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2) + "\n")
    return path


def run_bench(repo: Path, control: Path | None, root: Path, today: date, run: Runner, since: str = "") -> Path:
    require_dir(repo, "repo")
    if control is not None:
        require_dir(control, "control repo")
    windows = repo_windows(repo, read_kitfile(repo) or KitFile("", ()), run)
    columns = repo_columns(repo, windows, root, since, run)
    control_columns = None if control is None else repo_columns(control, windows, root, since, run)
    head = [f"# kit bench: {repo.name} ({today})", ""]
    lines = report_lines(columns, control_columns, [*BENCHMARKS, *MEASURES], NOT_MEASURED)
    path = repo / BENCH_DIR / f"{today}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([*head, *lines]) + "\n")
    return path
