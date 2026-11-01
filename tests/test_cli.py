from builders import request_kit_file

from kit import cli
from kit.cli import KIT_HOME, build_parser, main
from kit.errors import KitError
from kit.kitfile import write_kitfile


def test_version_prints_package_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "kit 0.4.0"


def test_kit_error_becomes_exit_1(capsys, monkeypatch):
    monkeypatch.setattr(cli, "dispatch", lambda args: (_ for _ in ()).throw(KitError("boom")))
    assert main(["status"]) == 1
    assert capsys.readouterr().err.strip() == "error: boom"


def test_request_parser_defaults_kit_home():
    args = build_parser().parse_args(["request", "a", "b", "r.md"])
    assert args.command == "request"
    assert args.kit_home == KIT_HOME


def test_request_from_a_repo_without_a_requests_section_is_exit_1(tmp_path, capsys):
    requester = tmp_path / "dividend-growth"
    write_kitfile(requester, request_kit_file())
    assert main(["request", str(requester), str(tmp_path / "investment"), str(tmp_path / "r.md")]) == 1
    assert "has no requests section" in capsys.readouterr().err
