"""UNIT: the testable parts of kit.insights_cmd: the plist, install and uninstall with a fake launchctl."""

from pathlib import Path

import pytest

from kit.errors import KitError
from kit.insights_cmd import LABEL, insights_plist, insights_program, install, notify_command, uninstall

FOUND = {"uv": "/u/uv", "claude": "/c/claude", "git": "/usr/bin/git"}.get


def test_program_runs_the_kit_checkout_with_notify(tmp_path):
    cmd = insights_program(Path("/kit"), Path("/base"), tmp_path, FOUND)
    assert cmd[:4] == ["/u/uv", "run", "--project", "/kit"]
    assert cmd[4:7] == ["kit", "insights", "run"] and cmd[-1] == "--notify"


def test_plist_runs_monday_at_nine_only(tmp_path):
    xml = insights_plist(Path("/kit"), Path("/base"), tmp_path, FOUND)
    assert xml.count("<key>Weekday</key>") == 1 and "<integer>1</integer><key>Hour</key><integer>9</integer>" in xml
    assert "<string>/c:/u:/usr/bin:/usr/bin:/bin</string>" in xml


def test_missing_tool_is_an_error(tmp_path):
    with pytest.raises(KitError, match="claude not found.*kit insights install"):
        insights_plist(Path("/kit"), Path("/base"), tmp_path, {"uv": "/u/uv"}.get)


def test_install_writes_and_loads_then_uninstall_removes(tmp_path):
    calls: list[list[str]] = []

    def launchctl(cmd: list[str], cwd: Path) -> str:
        calls.append(cmd)
        return ""

    plist = install(Path("/kit"), Path("/base"), tmp_path / "home", tmp_path / "agents", launchctl, FOUND)
    assert plist == tmp_path / "agents" / f"{LABEL}.plist" and plist.is_file()
    assert (tmp_path / "home" / "insights").is_dir()
    assert [c[1] for c in calls] == ["bootout", "bootstrap"]
    uninstall(Path("/kit"), tmp_path / "agents", None)
    assert not plist.exists()


def test_notify_names_the_report():
    assert notify_command(Path("/r.md"))[-1] == "report ready: /r.md"
