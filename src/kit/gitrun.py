"""Run a command and return its stdout; the injectable seam for git."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from kit.errors import KitError

Runner = Callable[[list[str], Path], str]


def run(cmd: list[str], cwd: Path) -> str:
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        raise KitError(f"{' '.join(cmd)} failed: {lines[0] if lines else 'no error output'}")
    return done.stdout


def require_dir(path: Path, role: str) -> Path:
    if not path.is_dir():
        raise KitError(f"{role} not found: {path}")
    return path
