"""Starter files, read from the version tag so an apply is a function of the version, copied only where missing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner

STARTER_DIR = "starter"
PERMISSIONS = "permissions.json"


@dataclass(frozen=True)
class Starter:
    permissions: dict
    files: dict[str, str]


def read_starter(kit_repo: Path, version: str, run: Runner) -> Starter:
    names = run(["git", "ls-tree", "-r", "--name-only", version, "--", f"{STARTER_DIR}/"], kit_repo).splitlines()
    relative = [name.removeprefix(f"{STARTER_DIR}/") for name in names]
    if PERMISSIONS not in relative:
        raise KitError(f"{version}: {STARTER_DIR}/{PERMISSIONS} is missing")
    texts = {name: run(["git", "show", f"{version}:{STARTER_DIR}/{name}"], kit_repo) for name in relative}
    return Starter(json.loads(texts.pop(PERMISSIONS)), texts)


def copy_missing(repo: Path, files: dict[str, str]) -> list[str]:
    added = [name for name in files if not (repo / name).exists()]
    for name in added:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(files[name])
    return added
