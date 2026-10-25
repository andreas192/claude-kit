"""The advisor: one read-only Sonnet session that turns the numbers-only report into concrete changes to the kit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kit.loop.stream import StageCost, stage_cost

MAX_BULLETS = 8
ERROR_MAX = 300
SETTINGS = {"permissions": {"allow": ["Read", "Grep", "Glob"], "deny": ["Bash", "Edit", "Write", "WebFetch", "WebSearch", "Agent"]}}
KIT_FILES = (
    "src/kit/loop/stream.py (STAGE_MODELS: model and effort per loop stage)",
    "src/kit/loop/prompts/*.md (the loop's stage prompts)",
    "src/kit/loop/base-settings.json (loop permissions)",
    "plugin/agents/*.md (implementer and reviewer subagents)",
    "plugin/hooks/*.mjs (context-warn and test-layer-guard)",
    "starter/docs/token-strategy.md (token rules applied to each repo)",
)

PROMPT = """You advise on the cost and flow of a Claude Code setup called the kit. Below is this week's report: loop stage \
costs, interactive-session benchmarks (B/F/Q/S rows, with targets in kit's bench) and findings from fixed rules.

Read only what you need from these kit files (paths relative to the current directory):
{files}

Reply with at most {max} markdown bullets and nothing else. Each bullet is one concrete change:
`- **<finding key or NEW>** <file>: <the change>. Why: <a number from the report>.`
Prefer changes that cut tokens or owner prompts without lowering quality. Skip a finding you cannot tie to a file.

{report}"""


@dataclass(frozen=True)
class Advice:
    bullets: list[str]
    cost: StageCost | None
    error: str  # "" when the advisor answered


def advisor_prompt(report: str) -> str:
    files = "\n".join(f"- {f}" for f in KIT_FILES)
    return PROMPT.format(files=files, max=MAX_BULLETS, report=report)


def write_settings(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "advisor-settings.json"
    path.write_text(json.dumps(SETTINGS, indent=2) + "\n")
    return path


def advisor_command(prompt: str, settings: Path) -> list[str]:
    return [
        "claude", "-p", prompt, "--model", "sonnet", "--effort", "medium",
        "--output-format", "json", "--permission-mode", "dontAsk", "--settings", str(settings),
    ]


def parse_advice(stdout: str) -> Advice:
    """The bullets of a `--output-format json` reply; an error string when it failed or had none."""
    try:
        final = json.loads(stdout)
    except ValueError:
        return Advice([], None, "advisor gave no JSON")
    if not isinstance(final, dict):
        return Advice([], None, "advisor gave no JSON object")
    cost = stage_cost(final)
    text = str(final.get("result") or "")
    if final.get("is_error"):
        return Advice([], cost, f"advisor failed: {text[:ERROR_MAX]}")
    bullets = [line.rstrip() for line in text.splitlines() if line.startswith("- ")][:MAX_BULLETS]
    return Advice(bullets, cost, "" if bullets else "advisor gave no bullets")


def advice_lines(advice: Advice) -> list[str]:
    footer = f"_Advisor: ${advice.cost.usd:.2f}, {advice.cost.turns} turns._" if advice.cost else ""
    body = advice.bullets or [f"_{advice.error}_"]
    return [*body, *(["", footer] if footer else [])]
