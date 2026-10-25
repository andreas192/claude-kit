"""UNIT: kit.insights.advise."""

import json

import pytest

from kit.insights.advise import MAX_BULLETS, advice_lines, advisor_command, advisor_prompt, parse_advice, write_settings

USAGE = {"input_tokens": 1, "cache_creation_input_tokens": 2, "cache_read_input_tokens": 3, "output_tokens": 4}


def reply(text: str, is_error: bool = False) -> str:
    return json.dumps({"type": "result", "is_error": is_error, "result": text, "total_cost_usd": 0.25, "duration_ms": 1, "num_turns": 4, "session_id": "a", "usage": USAGE})


def test_prompt_holds_the_report_and_the_kit_files():
    prompt = advisor_prompt("| B1 | 90 |")
    assert prompt.endswith("| B1 | 90 |") and "src/kit/loop/prompts/*.md" in prompt


def test_command_is_read_only_sonnet_json(tmp_path):
    settings = write_settings(tmp_path)
    assert json.loads(settings.read_text())["permissions"]["allow"] == ["Read", "Grep", "Glob"]
    cmd = advisor_command("p", settings)
    assert cmd[:3] == ["claude", "-p", "p"] and "sonnet" in cmd and "dontAsk" in cmd and cmd[-1] == str(settings)


def test_bullets_are_kept_and_capped():
    text = "intro\n" + "\n".join(f"- change {i}" for i in range(MAX_BULLETS + 2))
    advice = parse_advice(reply(text))
    assert len(advice.bullets) == MAX_BULLETS and advice.error == "" and advice.cost.usd == 0.25
    assert advice_lines(advice)[-1] == "_Advisor: $0.25, 4 turns._"


@pytest.mark.parametrize(
    ("stdout", "error"),
    [("not json", "advisor gave no JSON"), ("[]", "advisor gave no JSON object"), (reply("x", True), "advisor failed: x"), (reply("no bullets"), "advisor gave no bullets")],
)
def test_failures_become_one_line(stdout, error):
    advice = parse_advice(stdout)
    assert advice.bullets == [] and advice.error == error
    assert advice_lines(advice)[0] == f"_{error}_"
