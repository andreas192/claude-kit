"""UNIT: kit.kit_command, the command agents run kit with and the rewrite of bare `kit <cmd>` in a repo's docs."""

from pathlib import Path

import pytest

from kit.kit_command import DEFAULT_COMMAND, command_for, kit_command, rewrite_docs, rewrite_text, with_command

CMD = "uv run --project /k kit"


def test_kit_command_runs_the_given_checkout() -> None:
    assert kit_command(Path("/k")) == CMD


@pytest.mark.parametrize(
    "before,after",
    [
        ("`kit roadmap <repo>` validates", f"`{CMD} roadmap <repo>` validates"),
        ("run `kit request` (see", f"run `{CMD} request` (see"),
        ("a `kit loop status .` b `kit bench`", f"a `{CMD} loop status .` b `{CMD} bench`"),
    ],
)
def test_code_spans_get_the_full_command(before: str, after: str) -> None:
    assert rewrite_text(before, CMD) == (after, [1])


def test_code_block_lines_get_the_full_command() -> None:
    text = "```sh\n  kit roadmap .   # check\n```\n"
    assert rewrite_text(text, CMD) == (f"```sh\n  {CMD} roadmap .   # check\n```\n", [2])


@pytest.mark.parametrize(
    "text",
    [
        "`uv run --project ~/x kit roadmap .`",
        "uv run --project ~/x kit roadmap .",
        "the `kit:implementer-haiku` agent",
        "`kit` is a tool",
        "`kit frobnicate`",
        "a kit roadmap in prose",
        "`claude-kit roadmap`",
    ],
)
def test_text_that_is_not_a_bare_command_is_kept(text: str) -> None:
    assert rewrite_text(text, CMD) == (text, [])


def test_rewrite_docs_covers_claude_md_and_top_level_docs_only(tmp_path: Path) -> None:
    (tmp_path / "docs" / "superpowers").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text("x\nrun `kit request`\n")
    (tmp_path / "docs" / "roadmap.md").write_text("`kit roadmap .`\n")
    (tmp_path / "docs" / "superpowers" / "spec.md").write_text("`kit roadmap .`\n")
    (tmp_path / "README.md").write_text("`kit roadmap .`\n")
    assert rewrite_docs(tmp_path, CMD) == ["CLAUDE.md:2", "docs/roadmap.md:1"]
    assert (tmp_path / "CLAUDE.md").read_text() == f"x\nrun `{CMD} request`\n"
    assert (tmp_path / "docs" / "superpowers" / "spec.md").read_text() == "`kit roadmap .`\n"


def test_with_command_fills_the_starter_default() -> None:
    files = {"docs/roadmap.md": f"`{DEFAULT_COMMAND} roadmap <repo>` and `{DEFAULT_COMMAND} request`"}
    assert with_command(files, CMD) == {"docs/roadmap.md": f"`{CMD} roadmap <repo>` and `{CMD} request`"}


def test_command_for_reads_the_recorded_command(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "kit.json").write_text('{"test_command": "t", "applies": [], "kit_command": "uv run --project /k kit"}')
    assert command_for(tmp_path) == CMD


def test_command_for_falls_back_to_the_default(tmp_path: Path) -> None:
    assert command_for(tmp_path) == DEFAULT_COMMAND
