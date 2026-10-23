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


def session(peak: int, agents: list[tuple[str, str, str]] = (), start: str = "2026-10-17") -> Session:
    main = Transcript(calls=[Call("opus", 0, 0, peak, 1)], start=start, prompts=1)
    subs = [Subagent(kind, desc, Transcript(calls=[Call(model, 5, 1000, 0, 1)])) for kind, desc, model in agents]
    return Session("s", main, subs)
