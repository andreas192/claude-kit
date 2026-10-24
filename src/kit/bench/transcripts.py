"""Claude Code session transcripts: parsed into calls, transcripts, subagents and sessions.

Read-only. Keeps counts and token usage, never message text. Standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

BIG_RESULT_CHARS = 20_000
PERMISSION_DENIED = re.compile(r"^Permission for this action was denied|doesn't want to proceed")
HOOK_DENIED = re.compile(r"^\w+:\w+ hook error:")
CONTEXT_WARN = "Context is "
WARN_ATTACHMENTS = ("hook_system_message", "hook_additional_context")
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
    permission_denials: int = 0
    hook_denials: int = 0
    context_warnings: int = 0
    failed_test_runs: int = 0
    last_text: str = ""


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


def result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def result_chars(content: object) -> int:
    return len(result_text(content))


def dict_blocks(content: object) -> list[dict]:
    """The dict blocks of a message's content; anything else (strings, numbers, null) is skipped."""
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def count_tool_result(block: dict, transcript: Transcript, test_ids: Collection[str]) -> None:
    text = result_text(block.get("content"))
    transcript.big_results += len(text) > BIG_RESULT_CHARS
    if not block.get("is_error"):
        return
    transcript.permission_denials += bool(PERMISSION_DENIED.search(text))
    transcript.hook_denials += bool(HOOK_DENIED.search(text))
    transcript.failed_test_runs += block.get("tool_use_id") in test_ids


def count_user_record(record: dict, transcript: Transcript, test_ids: Collection[str] = ()) -> None:
    content = record.get("message", {}).get("content")
    if isinstance(content, str):
        transcript.prompts += not record.get("isMeta")
        return
    for block in dict_blocks(content):
        if block.get("type") == "tool_result":
            count_tool_result(block, transcript, test_ids)
        elif block.get("type") == "text":
            transcript.prompts += 1


def count_attachment(record: dict, transcript: Transcript) -> None:
    attachment = record.get("attachment") or {}
    if attachment.get("type") not in WARN_ATTACHMENTS:
        return
    content = attachment.get("content")
    texts = content if isinstance(content, list) else [content]
    transcript.context_warnings += any(isinstance(t, str) and t.startswith(CONTEXT_WARN) for t in texts)


def tool_command(block: dict) -> str:
    return (block.get("input") or {}).get("command") or ""


def test_command_ids(blocks: list, test_command: str) -> set[str]:
    """Ids of the Bash tool_use blocks whose command contains the repo's test command."""
    return {
        b["id"]
        for b in dict_blocks(blocks)
        if test_command and b.get("id") and b.get("type") == "tool_use" and b.get("name") == "Bash" and test_command in tool_command(b)
    }


def note_assistant_message(message: dict, transcript: Transcript, state: dict) -> None:
    """Track the text blocks of the latest message id (streamed records of one message share an id)."""
    blocks = dict_blocks(message.get("content"))
    if message.get("id") != state.get("id"):
        state["id"], state["texts"] = message.get("id"), []
    state["texts"] += [t for b in blocks if b.get("type") == "text" and (t := b.get("text", "")) not in state["texts"]]
    transcript.last_text = "\n".join(state["texts"])


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
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def parse_transcript(lines: Iterable[str], test_command: str = "") -> Transcript:
    """One call per message.id (streamed records repeat it; the last one wins), in first-seen order."""
    transcript, by_id, test_ids, last_message = Transcript(), {}, set(), {}
    for record in json_records(lines):
        timestamp = record.get("timestamp", "")
        transcript.start = transcript.start or timestamp
        transcript.end = timestamp or transcript.end
        if record.get("type") == "user":
            count_user_record(record, transcript, test_ids)
        elif record.get("type") == "attachment":
            count_attachment(record, transcript)
        elif record.get("type") == "assistant":
            message = record.get("message", {})
            test_ids |= test_command_ids(message.get("content") or [], test_command)
            note_assistant_message(message, transcript, last_message)
            call = usage_call(message)
            if call and message.get("id"):
                by_id[message["id"]] = call
    transcript.calls = list(by_id.values())
    return transcript


def read_transcript(path: Path, test_command: str = "") -> Transcript:
    with path.open(errors="ignore") as handle:
        return parse_transcript(handle, test_command)


def read_meta(path: Path) -> dict:
    """A subagent's `.meta.json`; missing, unreadable or not an object -> {}."""
    try:
        meta = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def read_subagent(path: Path, test_command: str = "") -> Subagent:
    meta_path = path.with_name(path.name.removesuffix(".jsonl") + ".meta.json")
    meta = read_meta(meta_path)
    return Subagent(meta.get("agentType", ""), meta.get("description", ""), read_transcript(path, test_command))


def load_sessions(project_dir: Path, test_command: str = "") -> list[Session]:
    sessions = []
    for path in sorted(project_dir.glob("*.jsonl")):
        main = read_transcript(path, test_command)
        if not main.calls:
            continue
        sub_paths = sorted((project_dir / path.stem / "subagents").glob("agent-*.jsonl"))
        sessions.append(Session(path.stem, main, [read_subagent(p, test_command) for p in sub_paths]))
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
