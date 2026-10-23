"""UNIT: kit.gitrun.require_dir, the typed error for a repo path that does not exist."""

import pytest

from kit.errors import KitError
from kit.gitrun import require_dir


def test_existing_directory_is_returned(tmp_path):
    assert require_dir(tmp_path, "repo") == tmp_path


def test_missing_path_is_a_kit_error_naming_the_role(tmp_path):
    with pytest.raises(KitError, match="control repo not found"):
        require_dir(tmp_path / "missing", "control repo")


def test_run_input_feeds_stdin_and_merges_env_over_the_process_env(tmp_path):
    from kit.gitrun import run_input

    done = run_input(["sh", "-c", "cat; echo $KIT_PROBE:$HOME"], tmp_path, "hello ", {"KIT_PROBE": "x"})
    assert done.returncode == 0 and done.stdout.startswith("hello x:") and len(done.stdout) > len("hello x:\n")


def test_run_input_does_not_raise_on_failure(tmp_path):
    from kit.gitrun import run_input

    assert run_input(["sh", "-c", "exit 3"], tmp_path, "", {}).returncode == 3
