"""Claude Code session transcripts: parsed into calls, transcripts, subagents and sessions.

Read-only. Keeps counts and token usage, never message text. Standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

BIG_RESULT_CHARS = 20_000
# Cost proxy in "fresh-input tokens": cache write 1.25x, cache read 0.1x, output 5x.
WEIGHTS = {"fresh": 1.0, "write": 1.25, "read": 0.1, "output": 5.0}


@dataclass(frozen=True)
class Call:
    model: str
    fresh: int
    write: int
    read: int
    output: int

    @property
    def context(self) -> int:
        return self.fresh + self.write + self.read

    @property
    def cost(self) -> float:
        return (
            WEIGHTS["fresh"] * self.fresh
            + WEIGHTS["write"] * self.write
            + WEIGHTS["read"] * self.read
            + WEIGHTS["output"] * self.output
        )


@dataclass
class Transcript:
    calls: list[Call] = field(default_factory=list)
    big_results: int = 0
    prompts: int = 0
    start: str = ""
    end: str = ""


@dataclass(frozen=True)
class Subagent:
    agent_type: str
    description: str
    transcript: Transcript

    @property
    def model(self) -> str:
        return self.transcript.calls[0].model if self.transcript.calls else ""


@dataclass(frozen=True)
class Session:
    session_id: str
    main: Transcript
    subagents: list[Subagent]


def model_family(model: str | None) -> str:
    name = (model or "").lower()
    for family in ("opus", "sonnet", "haiku"):
        if family in name:
            return family
    return ""


def result_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


def count_user_record(record: dict, transcript: Transcript) -> None:
    content = record.get("message", {}).get("content")
    if isinstance(content, str):
        transcript.prompts += not record.get("isMeta")
        return
    for block in content or []:
        if block.get("type") == "tool_result":
            transcript.big_results += result_chars(block.get("content")) > BIG_RESULT_CHARS
        elif block.get("type") == "text":
            transcript.prompts += 1


def usage_call(message: dict) -> Call | None:
    usage, family = message.get("usage"), model_family(message.get("model"))
    if not usage or not family:
        return None
    get = lambda key: int(usage.get(key) or 0)  # noqa: E731
    return Call(
        family,
        get("input_tokens"),
        get("cache_creation_input_tokens"),
        get("cache_read_input_tokens"),
        get("output_tokens"),
    )


def json_records(lines: Iterable[str]) -> Iterator[dict]:
    for line in lines:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def parse_transcript(lines: Iterable[str]) -> Transcript:
    """One call per message.id (streamed records repeat it; the last one wins), in first-seen order."""
    transcript, by_id = Transcript(), {}
    for record in json_records(lines):
        timestamp = record.get("timestamp", "")
        transcript.start = transcript.start or timestamp
        transcript.end = timestamp or transcript.end
        if record.get("type") == "user":
            count_user_record(record, transcript)
        elif record.get("type") == "assistant":
            message = record.get("message", {})
            call = usage_call(message)
            if call and message.get("id"):
                by_id[message["id"]] = call
    transcript.calls = list(by_id.values())
    return transcript


def read_transcript(path: Path) -> Transcript:
    with path.open(errors="ignore") as handle:
        return parse_transcript(handle)


def read_subagent(path: Path) -> Subagent:
    meta_path = path.with_name(path.name.removesuffix(".jsonl") + ".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return Subagent(meta.get("agentType", ""), meta.get("description", ""), read_transcript(path))


def load_sessions(project_dir: Path) -> list[Session]:
    sessions = []
    for path in sorted(project_dir.glob("*.jsonl")):
        main = read_transcript(path)
        if not main.calls:
            continue
        sub_paths = sorted((project_dir / path.stem / "subagents").glob("agent-*.jsonl"))
        sessions.append(Session(path.stem, main, [read_subagent(p) for p in sub_paths]))
    return sessions


def agent_kind(agent_type: str) -> str:
    """An agent type without its plugin prefix: 'kit:implementer-haiku' -> 'implementer-haiku'."""
    return agent_type.rpartition(":")[2]


def transcript_dir_name(repo: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(repo.resolve()))


def main_checkout(repo: Path) -> Path:
    """A git worktree's main checkout (its `.git` file points into `<main>/.git/worktrees/<name>`)."""
    git = repo / ".git"
    if not git.is_file():
        return repo
    gitdir = Path(git.read_text().removeprefix("gitdir:").strip())
    return gitdir.parents[2] if gitdir.parent.name == "worktrees" else repo


def project_dirs(root: Path, repo: Path) -> list[Path]:
    """The repo's transcript dir plus those of its worktrees (same prefix)."""
    base = transcript_dir_name(repo)
    return sorted(d for d in root.glob(base + "*") if d.name == base or d.name.startswith(base + "--"))
