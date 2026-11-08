# <Project>

## Stack

## Rules to follow

## Testing

Test command: see `.claude/kit.json` `test_command`.

## Working conventions

Roadmap: docs/roadmap.md. The PR that lands an item sets its Status to done and fills in Spec, Plan and PR. If the item has `Requested by`, tell the owner to update that repo's roadmap.

To ask another repo for a fix or a feature, write the item to a file in the scratch folder and run `uv run --project ~/Projects/Personal/claude-kit kit request <this repo> <target repo> <request file>` (the request file format is in `docs/command.md` of the kit checkout that command names); never edit another repo's files. Show the PR URL in your reply.
