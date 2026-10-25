"""Wiring for `kit insights run`: ledgers + transcripts + git history of every kit repo -> one weekly report."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from kit.bench.benchmarks import peak_context
from kit.bench.gitlog import followed_by_fix, history
from kit.bench.report import Column
from kit.bench.run import repo_sessions, repo_windows
from kit.bench.windows import assign, fix_share
from kit.gitrun import Runner
from kit.insights.advise import advice_lines, advisor_prompt, parse_advice
from kit.insights.findings import Week, findings
from kit.insights.loopstats import by_version, by_window, loop_session_ids, loop_stats
from kit.insights.report import repo_section, report_text
from kit.insights.weeks import applied_in, last_weeks
from kit.kitfile import KitFile, read_kitfile
from kit.loop.ledger import read_ledger
from kit.loop_cmd import runtime_dir
from kit.status import INVALID, find_kit_repos

INSIGHTS_DIR = "insights"
Advisor = Callable[[str], str]  # prompt -> the `claude -p --output-format json` stdout


def repo_section_lines(repo: Path, runtime: Path, root: Path, today: date, count: int, run: Runner) -> list[str]:
    kit = read_kitfile(repo) or KitFile("", ())
    entries = read_ledger(runtime)
    loop_ids = loop_session_ids(entries)
    sessions = repo_sessions(repo, root, kit.test_command)
    peaks = {s.session_id: peak_context(s.main) for s in sessions if s.session_id in loop_ids}
    interactive = [s for s in sessions if s.session_id not in loop_ids]
    weeks, versions = last_weeks(today, count), repo_windows(repo, kit, run)
    loop_weeks, session_weeks = by_window(entries, weeks), assign(interactive, weeks)
    ms = history(repo, run)
    flags = followed_by_fix(ms)
    rows = [
        Week(w.name, loop_stats(loop_weeks[w.name], peaks), session_weeks[w.name], applied_in(w, versions), fix_share(w, ms, flags))
        for w in weeks
    ]
    by_kit = assign(interactive, versions)
    session_versions = [Column(v.name, by_kit[v.name], fix_share(v, ms, flags)) for v in versions]
    loop_versions = [(v, loop_stats(es, peaks)) for v, es in by_version(entries).items()]
    return repo_section(repo.name, rows, loop_versions, session_versions, findings(rows))


def run_insights(base: Path, kit_home: Path, root: Path, today: date, count: int, advisor: Advisor | None, run: Runner) -> Path:
    repos = [base / r.name for r in find_kit_repos(base) if r.version != INVALID]
    title = last_weeks(today, 1)[0].name
    sections = [repo_section_lines(r, runtime_dir(kit_home, r), root, today, count, run) for r in repos]
    advice = advice_lines(parse_advice(advisor(advisor_prompt(report_text(title, sections, []))))) if advisor else []
    path = kit_home / INSIGHTS_DIR / f"{title}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_text(title, sections, advice))
    return path
