"""Reading a `claude -p` session: the stream-json lines, the LOOP reply and the usage windows."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

LIMIT = 0.8
DETAIL_MAX = 500
RESULT_MAX = 600
_LOOP = re.compile(r"^LOOP: (ok|more|park)\b\s*(.*)$")

STAGE_MODELS = {
    "probe": ("haiku", None),
    "spec": ("opus", "high"),
    "plan": ("opus", "medium"),
    "build": ("sonnet", "medium"),
    "pr": ("sonnet", "medium"),
}


@dataclass
class Usage:
    five_hour: float
    seven_day: float


@dataclass
class StageResult:
    outcome: str
    detail: str
    usage: Usage | None


def _loop_line(text: str) -> tuple[str, str]:
    found = ("error", "no LOOP line")
    for line in text.splitlines():
        m = _LOOP.match(line.strip())
        if m:
            found = (m.group(1), m.group(2).strip())
    return found


def _usage(info: dict) -> Usage | None:
    try:
        w = info["unifiedWindows"]
        five, seven = w["five_hour"]["utilization"], w["seven_day"]["utilization"]
    except (KeyError, TypeError):
        return None
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in (five, seven)):
        return None
    return Usage(float(five), float(seven))


def parse_stream(lines: Iterable[str]) -> StageResult:
    usage: Usage | None = None
    rejected = False
    final: dict | None = None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "rate_limit_event":
            info = event.get("rate_limit_info", {})
            rejected = rejected or info.get("status") == "rejected"
            usage = _usage(info)
        elif event.get("type") == "result":
            final = event
    if rejected or (final and final.get("is_error") and final.get("api_error_status") == 429):
        return StageResult("usage", "usage limit reached", usage)
    if final is None:
        return StageResult("error", "no result line", usage)
    if final.get("is_error"):
        return StageResult("error", f"session failed: {str(final.get('result') or '')[:RESULT_MAX]}", usage)
    outcome, detail = _loop_line(final.get("result") or "")
    return StageResult(outcome, detail, usage)


def over_limit(usage: Usage | None) -> bool:
    return usage is None or usage.five_hour >= LIMIT or usage.seven_day >= LIMIT


def _has_result(lines: list[str]) -> bool:
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            return True
    return False


def failure_line(why: str) -> str:
    return json.dumps({"type": "result", "is_error": True, "api_error_status": None, "result": why})


def stream_lines(stdout: str, code: int, stderr: str) -> list[str]:
    lines = stdout.splitlines()
    if not _has_result(lines):
        lines.append(failure_line(f"claude exited {code}: {stderr[-DETAIL_MAX:]}"))
    return lines


def claude_command(stage: str, text: str, settings: Path) -> list[str]:
    model, effort = STAGE_MODELS[stage]
    cmd = ["claude", "-p", text, "--model", model]
    if effort:
        cmd += ["--effort", effort]
    cmd += ["--output-format", "stream-json", "--verbose", "--permission-mode", "dontAsk"]
    return cmd + ["--settings", str(settings)]
