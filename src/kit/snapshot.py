"""Immutable per-version snapshots: a tag's plugin/ folder exported as a local plugin marketplace."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from kit.errors import KitError
from kit.gitrun import Runner

VERSION_PATTERN = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
PLUGIN_NAME = "kit"
STAGE_NAME = "snapshot"


def parse_version(version: str) -> tuple[int, int, int]:
    found = VERSION_PATTERN.fullmatch(version)
    if not found:
        raise KitError(f"not a release version: {version!r} (expected vMAJOR.MINOR.PATCH)")
    major, minor, patch = found.groups()
    return int(major), int(minor), int(patch)


def marketplace_name(version: str) -> str:
    major, minor, patch = parse_version(version)
    return f"kit-v{major}-{minor}-{patch}"


def latest_tag(kit_repo: Path, run: Runner) -> str:
    tags = [t for t in run(["git", "tag", "--list", "v*"], kit_repo).split() if VERSION_PATTERN.fullmatch(t)]
    if not tags:
        raise KitError("no release tag")
    return max(tags, key=parse_version)


def tree_digest(path: Path) -> str:
    """SHA-256 over the sorted relative paths and bytes of every file under path."""
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file() or p.is_symlink()):
        name = file.relative_to(path).as_posix().encode()
        body = os.readlink(file).encode() if file.is_symlink() else file.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name + len(body).to_bytes(8, "big") + body)
    return digest.hexdigest()


def export_plugin(kit_repo: Path, version: str, work: Path, stage: Path, run: Runner) -> None:
    """Extract the tag's plugin/ folder into stage/plugins/kit; the tar stays outside stage."""
    archive = work / "plugin.tar"
    run(["git", "archive", "--format=tar", "-o", str(archive), f"{version}:plugin"], kit_repo)
    destination = stage / "plugins" / PLUGIN_NAME
    destination.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter="data")


def write_marketplace(stage: Path, version: str) -> None:
    manifest = {
        "name": marketplace_name(version),
        "owner": {"name": "claude-kit"},
        "plugins": [{"name": PLUGIN_NAME, "source": f"./plugins/{PLUGIN_NAME}", "description": f"claude-kit {version}"}],
    }
    folder = stage / ".claude-plugin"
    folder.mkdir()
    (folder / "marketplace.json").write_text(json.dumps(manifest, indent=2) + "\n")


def check_plugin_version(stage: Path, version: str) -> None:
    manifest = stage / "plugins" / PLUGIN_NAME / ".claude-plugin" / "plugin.json"
    try:
        declared = json.loads(manifest.read_text()).get("version")
    except (OSError, ValueError, AttributeError) as error:
        raise KitError(f"{version}: plugin/.claude-plugin/plugin.json is missing or unreadable: {error}") from error
    if declared != version.removeprefix("v"):
        raise KitError(f"{version}: plugin.json declares version {declared!r}, expected {version.removeprefix('v')!r}")


def install_snapshot(stage: Path, target: Path, version: str) -> Path:
    if not target.exists():
        os.replace(stage, target)
    elif tree_digest(stage) != tree_digest(target):
        raise KitError(f"snapshot {target} differs from tag {version}; it must never change. Move it aside and re-run.")
    return target


def snapshot(kit_repo: Path, version: str, kit_home: Path, run: Runner) -> Path:
    parse_version(version)
    kit_home.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=kit_home, prefix=".tmp-"))
    try:
        stage = work / STAGE_NAME
        export_plugin(kit_repo, version, work, stage, run)
        write_marketplace(stage, version)
        check_plugin_version(stage, version)
        return install_snapshot(stage, kit_home / version, version)
    finally:
        shutil.rmtree(work, ignore_errors=True)
