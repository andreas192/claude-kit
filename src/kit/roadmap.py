"""`docs/roadmap.md`: the standard roadmap format, parsed and validated."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from kit.errors import KitError

ROADMAP_PATH = Path("docs") / "roadmap.md"
STATUSES = ("open", "owner", "blocked", "active", "done", "dropped")
FIELDS = ("Status", "Blocked by", "Depends on", "Spec", "Plan", "PR")
NEEDS_BLOCKED_BY = ("owner", "blocked")
KEY_MAX = 50

_FIELD_LINE = re.compile(r"^- ([A-Za-z ]+):\s*(.*)$")


@dataclass(frozen=True)
class Item:
    title: str
    key: str
    section: str
    status: str
    blocked_by: str
    depends_on: tuple[str, ...]
    spec: str
    plan: str
    pr: str
    line: int


@dataclass(frozen=True)
class Roadmap:
    items: tuple[Item, ...]

    def by_title(self, title: str) -> Item:
        for item in self.items:
            if item.title == title:
                return item
        raise KitError(f"no roadmap item titled {title!r}")


@dataclass(frozen=True)
class Problem:
    line: int
    message: str


class RoadmapError(KitError):
    def __init__(self, problems: tuple[Problem, ...]):
        self.problems = problems
        super().__init__("\n".join(f"{ROADMAP_PATH.as_posix()}:{p.line}: {p.message}" for p in problems))


@dataclass(frozen=True)
class _Block:
    section: str
    title: str
    line: int
    fields: tuple[tuple[str, str], ...]


def item_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return key if len(key) <= KEY_MAX else key[: KEY_MAX + 1].rsplit("-", 1)[0]


def _blocks(text: str) -> list[_Block]:
    lines = [line.rstrip() for line in text.splitlines()]
    blocks: list[_Block] = []
    section = ""
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("### "):
            blocks.append(_Block(section, line[4:].strip(), number, _fields_after(lines, number)))
    return blocks


def _fields_after(lines: list[str], heading_number: int) -> tuple[tuple[str, str], ...]:
    fields = []
    for line in lines[heading_number:]:
        found = _FIELD_LINE.match(line)
        if not found:
            break
        fields.append((found.group(1), found.group(2).strip()))
    return tuple(fields)


def _field_problems(block: _Block) -> list[Problem]:
    values = {name: value for name, value in block.fields if name in FIELDS}
    problems = [Problem(block.line, f"unknown field {name!r}") for name, _ in block.fields if name not in FIELDS]
    status = values.get("Status", "")
    if "Status" not in values:
        problems.append(Problem(block.line, "missing Status"))
    elif status not in STATUSES:
        problems.append(Problem(block.line, f"unknown Status {status!r}"))
    elif status in NEEDS_BLOCKED_BY and not values.get("Blocked by"):
        problems.append(Problem(block.line, f"Blocked by is required when Status is {status}"))
    elif status not in NEEDS_BLOCKED_BY and "Blocked by" in values:
        problems.append(Problem(block.line, "Blocked by is only for owner or blocked"))
    return problems


def _duplicate_problems(blocks: list[_Block]) -> list[Problem]:
    seen: set[str] = set()
    problems = []
    for block in blocks:
        key = item_key(block.title)
        if key in seen:
            problems.append(Problem(block.line, f"duplicate key {key!r}"))
        seen.add(key)
    return problems


def _depends_on(block: _Block) -> tuple[str, ...]:
    value = dict(block.fields).get("Depends on", "")
    return tuple(title.strip() for title in value.split(",") if title.strip())


def _dependency_problems(blocks: list[_Block]) -> list[Problem]:
    titles = {block.title for block in blocks}
    return [
        Problem(block.line, f"Depends on {title!r} is not an item")
        for block in blocks
        for title in _depends_on(block)
        if title not in titles
    ]


def _item(block: _Block) -> Item:
    values = dict(block.fields)
    return Item(
        title=block.title,
        key=item_key(block.title),
        section=block.section,
        status=values.get("Status", ""),
        blocked_by=values.get("Blocked by", ""),
        depends_on=_depends_on(block),
        spec=values.get("Spec", ""),
        plan=values.get("Plan", ""),
        pr=values.get("PR", ""),
        line=block.line,
    )


def parse_roadmap(text: str) -> Roadmap:
    blocks = _blocks(text)
    problems = [p for block in blocks for p in _field_problems(block)]
    problems += _duplicate_problems(blocks) + _dependency_problems(blocks)
    if problems:
        raise RoadmapError(tuple(sorted(problems, key=lambda p: p.line)))
    return Roadmap(tuple(_item(block) for block in blocks))


def read_roadmap(repo: Path) -> Roadmap:
    path = repo / ROADMAP_PATH
    if not path.is_file():
        raise KitError(f"{path} not found")
    return parse_roadmap(path.read_text())
