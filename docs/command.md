# Commands

```sh
uv sync                  # create .venv from the lockfile (dev: pytest)
uv run pytest -q         # full offline test suite
```

The first `uv sync` or `uv run` downloads uv's own managed Python (the repo sets `python-preference = "only-managed"`), so it needs network once.

Run the kit against a repo from its own `.venv`:

```sh
uv run --project ~/Projects/Personal/claude-kit kit apply <repo> [--version vX.Y.Z]
uv run --project ~/Projects/Personal/claude-kit kit bench <repo> --control <repo>
uv run --project ~/Projects/Personal/claude-kit kit status
```

## Release

1. Bump the version in `plugin/.claude-plugin/plugin.json`, `pyproject.toml` and `src/kit/__init__.py`.
2. Commit, then `git tag vX.Y.Z`.
