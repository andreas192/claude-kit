# Roadmap

What this repo will build next, in priority order. `kit roadmap <repo>` validates this file and shows what the loop would pick next.

## How to add an item

Put each item under a `## ` section of any name, as a `### ` heading with a unique title. Right after the heading come field lines (`- Name: value`); free Markdown after them describes the item. The order in the file is the priority order.

Status is required and means:

- `open`: needs no decision from the owner. The loop takes only these, the first one in file order whose `Depends on` items are all `done`.
- `owner`: needs the owner (a decision, an input, or the owner's own hands). These are the weekend list. Add `Blocked by` with what it waits for.
- `blocked`: waits on something other than the owner, such as upstream data or another item. Add `Blocked by`.
- `active`: someone is working on it outside the loop.
- `done`: landed.
- `dropped`: will not be built.

Other fields: `Depends on` (comma-separated titles from this file), and `Spec`, `Plan`, `PR` (a path or URL). The PR that lands an item sets its Status to `done` and fills in Spec, Plan and PR. When unsure whether an item is `open`, mark it `owner`.

## Features
