"""UNIT: kit.loop.stream, over claude stream lines built in code."""

import json
from pathlib import Path

import pytest

from kit.loop.stream import STAGE_MODELS, Usage, claude_command, over_limit, parse_stream, stream_lines


def rate(five: float, seven: float = 0.1, status: str = "allowed") -> str:
    windows = {"five_hour": {"utilization": five}, "seven_day": {"utilization": seven}}
    info = {"status": status, "unifiedWindows": windows}
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": info})


def result(text: str, is_error: bool = False, api: int | None = None) -> str:
    return json.dumps({"type": "result", "is_error": is_error, "api_error_status": api, "result": text})


def test_parse_ok_with_detail_and_last_usage():
    r = parse_stream([rate(0.3), rate(0.5, 0.6), result("done\nLOOP: ok spec written")])
    assert (r.outcome, r.detail, r.usage) == ("ok", "spec written", Usage(0.5, 0.6))


def test_parse_takes_the_last_loop_line():
    assert parse_stream([result("LOOP: more\nLOOP: park tests red")]).outcome == "park"


def test_parse_no_loop_line_is_error():
    assert parse_stream([result("all done")]).outcome == "error"
    assert parse_stream(["garbage", rate(0.2)]).outcome == "error"  # no result line
    assert parse_stream([result("LOOP: maybe")]).outcome == "error"  # unknown word


def test_parse_pick_is_no_longer_a_loop_word():
    assert parse_stream([result("LOOP: pick Row A")]).outcome == "error"


def test_parse_rejected_is_usage():
    assert parse_stream([rate(1.0, status="rejected"), result("LOOP: ok")]).outcome == "usage"
    assert parse_stream([result("limit", is_error=True, api=429)]).outcome == "usage"
    assert parse_stream([result("boom", is_error=True, api=500)]).outcome == "error"


def test_parse_windowless_event_gives_unknown_usage():
    bare = json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}})
    nulled = rate(0.3).replace("0.3", "null")
    for last in (bare, nulled):
        r = parse_stream([rate(0.3), last, result("LOOP: ok")])
        assert (r.outcome, r.usage) == ("ok", None)


def test_parse_failed_session_is_error_despite_loop_line():
    assert parse_stream([result("LOOP: ok", is_error=True, api=500)]).outcome == "error"


@pytest.mark.parametrize(
    ("usage", "over"),
    [(None, True), (Usage(0.79, 0.5), False), (Usage(0.8, 0.1), True), (Usage(0.1, 0.8), True)],
)
def test_over_limit(usage, over):
    assert over_limit(usage) is over


def test_stream_lines_adds_exit_code_and_stderr_tail_when_no_result():
    lines = stream_lines("noise\n", 3, "x" * 900 + "TAIL")
    r = parse_stream(lines)
    assert r.outcome == "error" and "claude exited 3" in r.detail and "TAIL" in r.detail
    assert len(r.detail) < 600
    ok = result("LOOP: ok")
    assert stream_lines(ok, 0, "") == [ok]


def test_probe_command_has_no_effort_flag_and_others_do():
    probe = claude_command("probe", "x", Path("s.json"))
    assert "--effort" not in probe and "--setting-sources" not in probe
    assert "--effort" in claude_command("build", "x", Path("s.json"))


def test_stage_models_have_no_pick_stage_and_keep_the_others():
    assert STAGE_MODELS == {
        "probe": ("haiku", None),
        "spec": ("opus", "high"),
        "plan": ("opus", "medium"),
        "build": ("sonnet", "medium"),
        "pr": ("sonnet", "medium"),
    }


def test_command_carries_the_prompt_the_model_and_the_settings_file():
    cmd = claude_command("spec", "the prompt", Path("/r/settings.json"))
    assert cmd[:5] == ["claude", "-p", "the prompt", "--model", "opus"]
    assert cmd[-2:] == ["--settings", "/r/settings.json"]
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
