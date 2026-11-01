"""A cross-repo roadmap request: parse the request file, build the filed item, append it to a roadmap."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kit.errors import KitError
from kit.loop.driver import CO_AUTHOR
from kit.loop.prs import ATTRIBUTION
from kit.roadmap import FIELD_LINE, Item, Roadmap, item_key, parse_roadmap
from kit.snapshot import parse_version

MIN_TARGET_VERSION = "v0.4.0"
REQUESTS_SECTION = "## Requests"
TARGET_PREFIX = "Target: "
DROPPED_FIELDS = ("Status", "Blocked by", "Requested by", "Depends on")


class RequestError(KitError):
    pass


@dataclass(frozen=True)
class Request:
    target: str
    title: str
    key: str
    fields: tuple[tuple[str, str], ...]
    body: str


def _split_target(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    first = next((number for number, line in enumerate(lines) if line.strip()), len(lines))
    if first < len(lines) and lines[first].startswith(TARGET_PREFIX):
        return lines[first][len(TARGET_PREFIX) :].strip(), lines[first + 1 :]
    return "", lines


def _only_heading(lines: list[str]) -> int:
    if any(line.startswith("## ") for line in lines):
        raise RequestError("a request has no ## section, only one ### item")
    headings = [number for number, line in enumerate(lines) if line.startswith("### ")]
    if not headings:
        raise RequestError("a request has no ### item")
    if len(headings) > 1:
        raise RequestError("a request has exactly one ### item")
    if any(line.strip() for line in lines[: headings[0]]):
        raise RequestError("a request has text before the ### item; put it in the item's body")
    return headings[0]


def _fields_and_body(lines: list[str]) -> tuple[tuple[tuple[str, str], ...], str]:
    fields = []
    for number, line in enumerate(lines):
        found = FIELD_LINE.match(line.rstrip())
        if not found:
            return tuple(fields), "\n".join(lines[number:]).strip()
        if found.group(1) not in DROPPED_FIELDS:
            fields.append((found.group(1), found.group(2).strip()))
    return tuple(fields), ""


def parse_request(text: str) -> Request:
    target, lines = _split_target(text)
    heading = _only_heading(lines)
    title = lines[heading][4:].strip()
    key = item_key(title)
    if not key:
        raise RequestError(f"the ### title {title!r} has no letters or digits to name its branch")
    fields, body = _fields_and_body(lines[heading + 1 :])
    return Request(target, title, key, fields, body)


def filed_item(request: Request, requester: str) -> str:
    owner_fields = (
        ("Status", "owner"),
        ("Blocked by", f"the owner's review of a request from {requester}"),
        ("Requested by", requester),
    )
    lines = [f"### {request.title}", *(f"- {name}: {value}" for name, value in (*owner_fields, *request.fields))]
    tail = f"\n{request.body}\n" if request.body else ""
    return "\n".join(lines) + "\n" + tail


def _insert_in_section(lines: list[str], start: int, item: str) -> str:
    after = next((n for n in range(start + 1, len(lines)) if lines[n].startswith("## ")), len(lines))
    head = "".join(lines[:after]).rstrip("\n")
    rest = "".join(lines[after:])
    return f"{head}\n\n{item}" + (f"\n{rest}" if rest else "")


def _insert(roadmap_text: str, item_text: str) -> str:
    item = item_text.rstrip("\n") + "\n"
    lines = roadmap_text.splitlines(keepends=True)
    start = next((n for n, line in enumerate(lines) if line.rstrip() == REQUESTS_SECTION), None)
    if start is not None:
        return _insert_in_section(lines, start, item)
    head = roadmap_text.rstrip("\n")
    return f"{head}\n\n{REQUESTS_SECTION}\n\n{item}" if head else f"{REQUESTS_SECTION}\n\n{item}"


def with_request(roadmap_text: str, item_text: str) -> str:
    text = _insert(roadmap_text, item_text)
    parse_roadmap(text)
    return text


def existing_item(roadmap: Roadmap, key: str) -> Item | None:
    return next((item for item in roadmap.items if item.key == key), None)


def _resolved_targets(repo: Path, targets: tuple[str, ...]) -> list[Path]:
    return [(repo / target).resolve() for target in targets]


def allowed_target(repo: Path, targets: tuple[str, ...], target: Path) -> Path:
    resolved = target.resolve()
    if resolved not in _resolved_targets(repo, targets):
        raise KitError(f"{resolved} is not in requests.targets")
    return resolved


def target_by_name(repo: Path, targets: tuple[str, ...], name: str) -> Path:
    if not name:
        raise KitError("the request has no Target: line; add a first line `Target: <repo>`")
    found = next((path for path in _resolved_targets(repo, targets) if path.name == name), None)
    if found is None:
        raise KitError(f"{name!r} is not in requests.targets")
    return found


def require_version(latest: str | None, target_name: str) -> None:
    if latest is None or parse_version(latest) < parse_version(MIN_TARGET_VERSION):
        raise KitError(f"{target_name} has kit {latest or 'no version'}; apply {MIN_TARGET_VERSION} or later to {target_name} first")


def commit_message(requester: str, title: str) -> str:
    return f"roadmap: request from {requester}: {title}\n\n{CO_AUTHOR}"


def pr_title(requester: str, title: str) -> str:
    return f"request from {requester}: {title}"


def pr_body(item_text: str, requester: str, loop_branch: str) -> str:
    parts = [f"Roadmap request from `{requester}`, filed by `kit request`. The owner reviews it before it is picked up.", item_text.rstrip("\n")]
    if loop_branch:
        parts.append(f"Loop branch: `{loop_branch}`")
    parts.append(ATTRIBUTION)
    return "\n\n".join(parts) + "\n"
