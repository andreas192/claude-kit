"""Run a command and return its stdout; the injectable seam for git."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from kit.errors import KitError

NOT_RUNNABLE = 127
Runner = Callable[[list[str], Path], str]
RunInput = Callable[[list[str], Path, str, dict[str, str]], subprocess.CompletedProcess[str]]


def run(cmd: list[str], cwd: Path) -> str:
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        raise KitError(f"{' '.join(cmd)} failed: {lines[0] if lines else 'no error output'}")
    return done.stdout


def run_input(cmd: list[str], cwd: Path, stdin: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `cmd` with `stdin` text; never raises on a non-zero exit, callers read `returncode`.

    `env` is merged over `os.environ`, not a replacement, so PATH (and thus `node`, `sh`) still resolves.
    A program that cannot be started (not on PATH, not executable) yields returncode 127 with the reason on stderr.
    """
    try:
        return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, env={**os.environ, **env})
    except OSError as error:
        return subprocess.CompletedProcess(cmd, NOT_RUNNABLE, "", f"{cmd[0]}: not found ({error})")


def require_dir(path: Path, role: str) -> Path:
    if not path.is_dir():
        raise KitError(f"{role} not found: {path}")
    return path
