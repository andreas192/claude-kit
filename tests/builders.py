"""Helpers that build transcript records and sessions in code, shared by the bench unit tests."""

import json

from kit.bench.transcripts import Call, Session, Subagent, Transcript


def rec(timestamp: str) -> str:
    return json.dumps({"type": "system", "timestamp": timestamp})


def assistant(mid: str, model: str = "claude-opus-5-5", fresh: int = 10, write: int = 0, read: int = 0, out: int = 5) -> str:
    usage = {
        "input_tokens": fresh,
        "cache_creation_input_tokens": write,
        "cache_read_input_tokens": read,
        "output_tokens": out,
    }
    return json.dumps({"type": "assistant", "timestamp": "2026-10-17T07:00:00Z", "message": {"id": mid, "model": model, "usage": usage}})


def user(content: object, meta: bool = False) -> str:
    return json.dumps({"type": "user", "isMeta": meta, "message": {"content": content}})


def tool_use(tool_id: str, command: str) -> str:
    block = {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}
    return json.dumps({"type": "assistant", "message": {"id": "u" + tool_id, "content": [block]}})


def tool_result(tool_id: str, text: str, error: bool = False) -> str:
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": text, "is_error": error}
    return json.dumps({"type": "user", "message": {"content": [block]}})


def attachment(kind: str, content: object) -> str:
    return json.dumps({"type": "attachment", "attachment": {"type": kind, "content": content}})


def assistant_text(mid: str, text: str) -> str:
    return json.dumps({"type": "assistant", "message": {"id": mid, "content": [{"type": "text", "text": text}]}})


def reviewer(description: str, last_text: str) -> Subagent:
    return Subagent("kit:reviewer-sonnet", description, Transcript(calls=[Call("sonnet", 5, 1000, 0, 1)], last_text=last_text))


def implementer(description: str, failed_tests: int = 0) -> Subagent:
    transcript = Transcript(calls=[Call("sonnet", 5, 1000, 0, 1)], failed_test_runs=failed_tests)
    return Subagent("kit:implementer-sonnet", description, transcript)


def session(
    peak: int = 0,
    agents: list[tuple[str, str, str]] = (),
    start: str = "2026-10-17",
    end: str = "",
    subagents: list[Subagent] | None = None,
    prompts: int = 1,
) -> Session:
    main = Transcript(calls=[Call("opus", 0, 0, peak, 1)], start=start, end=end, prompts=prompts)
    subs = [Subagent(kind, desc, Transcript(calls=[Call(model, 5, 1000, 0, 1)])) for kind, desc, model in agents]
    return Session("s", main, subs + (subagents or []))
