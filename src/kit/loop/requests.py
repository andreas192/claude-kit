"""The runtime log `requests.json` of cross-repo requests the loop filed, kept per branch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kit.errors import KitError

REQUESTS_FILE = "requests.json"
REQUESTS_HEADING = "## Requests filed on other repos"


class RequestsLogError(KitError):
    pass


@dataclass(frozen=True)
class RequestRecord:
    target: str
    title: str
    url: str = ""
    error: str = ""


def _entry(record: RequestRecord) -> dict[str, str]:
    if bool(record.url) == bool(record.error):
        raise RequestsLogError(f"request {record.title!r} needs exactly one of url and error")
    outcome = {"url": record.url} if record.url else {"error": record.error}
    return {"target": record.target, "title": record.title, **outcome}


def _record(entry: object) -> RequestRecord:
    if not isinstance(entry, dict) or not all(isinstance(v, str) for v in entry.values()):
        raise ValueError
    record = RequestRecord(entry["target"], entry["title"], entry.get("url", ""), entry.get("error", ""))
    if bool(record.url) == bool(record.error):
        raise ValueError
    return record


def _load(runtime: Path) -> dict[str, list[object]]:
    path = runtime / REQUESTS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RequestsLogError(f"{path} is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
        raise RequestsLogError(f"{path} must map each branch to a list of requests")
    return data


def read_requests(runtime: Path, branch: str) -> list[RequestRecord]:
    entries = _load(runtime).get(branch, [])
    try:
        return [_record(e) for e in entries]
    except (KeyError, ValueError) as exc:
        raise RequestsLogError(f"{runtime / REQUESTS_FILE}: bad request entry for {branch}") from exc


def add_requests(runtime: Path, branch: str, records: list[RequestRecord]) -> None:
    data = _load(runtime)
    data[branch] = [*data.get(branch, []), *(_entry(r) for r in records)]
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / REQUESTS_FILE).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def request_lines(records: list[RequestRecord]) -> list[str]:
    return [
        f"- filed on {r.target}: {r.title}: {r.url}" if r.url else f"- failed on {r.target}: {r.title}: {r.error}"
        for r in records
    ]
