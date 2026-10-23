"""UNIT: kit.gitrun.require_dir, the typed error for a repo path that does not exist."""

import pytest

from kit.errors import KitError
from kit.gitrun import require_dir


def test_existing_directory_is_returned(tmp_path):
    assert require_dir(tmp_path, "repo") == tmp_path


def test_missing_path_is_a_kit_error_naming_the_role(tmp_path):
    with pytest.raises(KitError, match="control repo not found"):
        require_dir(tmp_path / "missing", "control repo")
