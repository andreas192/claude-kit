from kit import cli
from kit.cli import main
from kit.errors import KitError


def test_version_prints_package_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "kit 0.1.0"


def test_kit_error_becomes_exit_1(capsys, monkeypatch):
    monkeypatch.setattr(cli, "dispatch", lambda args: (_ for _ in ()).throw(KitError("boom")))
    assert main(["status"]) == 1
    assert capsys.readouterr().err.strip() == "error: boom"
