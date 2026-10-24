"""Edit a target repo's .claude/settings.json as JSON, never mutating the inputs."""
import copy
import json
import re
from pathlib import Path

from kit.errors import KitError
from kit.snapshot import marketplace_name

SETTINGS_PATH = Path(".claude") / "settings.json"
KIT_MARKETPLACE = re.compile(r"kit-v\d+-\d+-\d+")
KIT_PLUGIN = re.compile(r"kit@kit-v\d+-\d+-\d+")


def read_settings(repo: Path) -> dict:
    path = repo / SETTINGS_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise KitError(f"{path} is not valid JSON: {error}") from error


def write_settings(repo: Path, settings: dict) -> None:
    path = repo / SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def with_kit(settings: dict, version: str, snapshot_path: Path) -> dict:
    result = copy.deepcopy(settings)
    name = marketplace_name(version)
    markets = {k: v for k, v in result.get("extraKnownMarketplaces", {}).items() if not KIT_MARKETPLACE.fullmatch(k)}
    plugins = {k: v for k, v in result.get("enabledPlugins", {}).items() if not KIT_PLUGIN.fullmatch(k)}
    markets[name] = {"source": {"source": "directory", "path": str(snapshot_path)}}
    plugins[f"kit@{name}"] = True
    result["extraKnownMarketplaces"] = markets
    result["enabledPlugins"] = plugins
    return result


def without_hook_scripts(settings: dict, scripts: list[str]) -> tuple[dict, list[str]]:
    result = copy.deepcopy(settings)
    removed: list[str] = []
    events = {}
    for event, groups in result.get("hooks", {}).items():
        kept_groups = []
        for group in groups:
            kept = [h for h in group.get("hooks", []) if not _runs_script(h, scripts)]
            removed += [h["command"] for h in group.get("hooks", []) if _runs_script(h, scripts)]
            if kept:
                kept_groups.append({**group, "hooks": kept})
        if kept_groups:
            events[event] = kept_groups
    if events:
        result["hooks"] = events
    else:
        result.pop("hooks", None)
    return result, removed


def with_permissions(settings: dict, starter: dict) -> dict:
    result = copy.deepcopy(settings)
    if "permissions" not in result:
        result["permissions"] = copy.deepcopy(starter)
    return result


def _runs_script(hook: dict, scripts: list[str]) -> bool:
    command = hook.get("command", "")
    return any(f".claude/hooks/{script}" in command for script in scripts)
