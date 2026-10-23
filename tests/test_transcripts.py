"""UNIT: kit.bench.transcripts, over transcripts built in code."""

import json
from pathlib import Path

import pytest
from builders import assistant, rec, user

from kit.bench.transcripts import (
    Call,
    agent_kind,
    load_sessions,
    main_checkout,
    model_family,
    parse_transcript,
    project_dirs,
    transcript_dir_name,
)


def test_parse_counts_each_message_id_once_last_record_wins() -> None:
    t = parse_transcript([assistant("a", out=1), assistant("a", out=9), assistant("b")])
    assert [c.output for c in t.calls] == [9, 5]


def test_parse_skips_unknown_models_and_bad_lines() -> None:
    t = parse_transcript(["not json", assistant("a", model="<synthetic>"), assistant("b")])
    assert len(t.calls) == 1


def test_parse_records_start_prompts_and_big_results() -> None:
    big = [{"type": "tool_result", "content": "x" * 20_001}, {"type": "tool_result", "content": [{"type": "text", "text": "y"}]}]
    t = parse_transcript([assistant("a"), user("hi"), user("<cmd>", meta=True), user([{"type": "text", "text": "go"}]), user(big)])
    assert (t.start, t.prompts, t.big_results) == ("2026-10-17T07:00:00Z", 2, 1)


def test_end_is_the_last_timestamp() -> None:
    t = parse_transcript([rec("2026-10-17T07:00:00Z"), assistant("a"), rec("2026-10-17T08:30:00Z")])
    assert (t.start, t.end) == ("2026-10-17T07:00:00Z", "2026-10-17T08:30:00Z")


def test_end_ignores_records_without_a_timestamp() -> None:
    t = parse_transcript([rec("2026-10-17T07:00:00Z"), user("hi")])
    assert t.end == "2026-10-17T07:00:00Z"


def test_call_context_and_cost() -> None:
    call = Call("opus", fresh=100, write=1000, read=10_000, output=10)
    assert call.context == 11_100
    assert call.cost == pytest.approx(100 + 1250 + 1000 + 50)


@pytest.mark.parametrize(("model", "family"), [("claude-opus-5-5", "opus"), ("claude-haiku-4-5-2025", "haiku"), ("<synthetic>", ""), (None, "")])
def test_model_family(model: str | None, family: str) -> None:
    assert model_family(model) == family


def test_agent_kind_drops_the_plugin_prefix() -> None:
    assert [agent_kind(a) for a in ("kit:implementer-haiku", "implementer-haiku", "Explore")] == ["implementer-haiku", "implementer-haiku", "Explore"]


def test_load_sessions_reads_subagents_and_meta(tmp_path: Path) -> None:
    (tmp_path / "abc.jsonl").write_text(assistant("a") + "\n")
    (tmp_path / "empty.jsonl").write_text(user("hi") + "\n")
    agents = tmp_path / "abc" / "subagents"
    agents.mkdir(parents=True)
    (agents / "agent-1.jsonl").write_text(assistant("b", model="claude-sonnet-5-5") + "\n")
    (agents / "agent-1.meta.json").write_text(json.dumps({"agentType": "implementer-sonnet", "description": "Implement Task 1"}))
    [s] = load_sessions(tmp_path)
    assert (s.session_id, s.subagents[0].agent_type, s.subagents[0].model) == ("abc", "implementer-sonnet", "sonnet")


def test_transcript_dir_name_replaces_non_alphanumerics(tmp_path: Path) -> None:
    assert transcript_dir_name(Path("/x/my.repo")) == "-x-my-repo"


def test_project_dirs_include_worktrees_only(tmp_path: Path) -> None:
    repo = Path("/x/repo")
    for name in ("-x-repo", "-x-repo--worktrees", "-x-repo2"):
        (tmp_path / name).mkdir()
    assert [d.name for d in project_dirs(tmp_path, repo)] == ["-x-repo", "-x-repo--worktrees"]


def test_main_checkout_of_a_worktree(tmp_path: Path) -> None:
    main, wt = tmp_path / "main", tmp_path / "wt"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
    assert main_checkout(wt) == main
    assert main_checkout(main) == main
