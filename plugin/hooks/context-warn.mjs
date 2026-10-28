#!/usr/bin/env node
// Stop and UserPromptSubmit hook. Enforces the checkpoint
// ("hand off by file and /clear past ~60k"; docs/token-strategy.md if the repo has one): reads the session transcript, takes
// the context of the last main-window call, and warns once per 60k step
// (60k, 120k, ...) per event. Stop tells the owner; UserPromptSubmit tells Claude
// to write the handoff and end its reply with the line to paste after /clear.
// Read-only on the transcript; the only state is a small file per session and
// event in the OS temp dir.

import { readFileSync, writeFileSync, existsSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_STEP = 60000;
const STEP = Number(process.env.KIT_CONTEXT_WARN_STEP ?? DEFAULT_STEP);
const STRATEGY_DOC = "docs/token-strategy.md";

export function lastContext(lines) {
  for (let i = lines.length - 1; i >= 0; i--) {
    let record;
    try {
      record = JSON.parse(lines[i]);
    } catch {
      continue;
    }
    const usage = record?.message?.usage;
    if (record?.type !== "assistant" || record?.isSidechain || !usage) continue;
    if (!/opus|sonnet|haiku/i.test(record.message.model ?? "")) continue;
    return (usage.input_tokens ?? 0) + (usage.cache_creation_input_tokens ?? 0) + (usage.cache_read_input_tokens ?? 0);
  }
  return 0;
}

export function warnLevel(context, warned) {
  const level = Math.floor(context / STEP);
  return level >= 1 && level > warned ? level : 0;
}

export function messages(context, strategyDoc) {
  const k = Math.round(context / 1000);
  const step = Math.round(STEP / 1000);
  const docNote = strategyDoc ? ` (${STRATEGY_DOC})` : "";
  const checkpoint = strategyDoc ? `the ${step}k checkpoint in ${STRATEGY_DOC}` : `the ${step}k checkpoint`;
  return {
    owner:
      `Context is ${k}k tokens (checkpoint: ${step}k). On your next message Claude writes the handoff ` +
      `and gives you the line to paste after /clear${docNote}.`,
    claude:
      `Context is ${k}k tokens, past ${checkpoint}. Before anything else: ` +
      "1) write the handoff into the plan or spec this session works from (tasks done, decisions, the next step); " +
      "if there is none, say so and propose a file. " +
      "2) Do the owner's request only if it is small; otherwise leave it to the next session. " +
      "3) End the reply with exactly two lines: `Handoff: <file>` and " +
      "`After /clear, paste: continue from <file>, next: <step>`.",
  };
}

function main() {
  const input = JSON.parse(readFileSync(0, "utf8"));
  const path = input?.transcript_path;
  if (!path || !existsSync(path)) return;
  const context = lastContext(readFileSync(path, "utf8").split("\n"));
  const event = input.hook_event_name === "UserPromptSubmit" ? "prompt" : "stop";
  const state = join(tmpdir(), `kit-context-warn-${input.session_id ?? "unknown"}-${event}`);
  const warned = existsSync(state) ? Number(readFileSync(state, "utf8")) || 0 : 0;
  const level = warnLevel(context, warned);
  if (!level) return;
  writeFileSync(state, String(level));
  const strategyDoc = existsSync(join(process.env.CLAUDE_PROJECT_DIR ?? "", STRATEGY_DOC));
  const text = messages(context, strategyDoc);
  const out =
    event === "prompt"
      ? { hookSpecificOutput: { hookEventName: "UserPromptSubmit", additionalContext: text.claude } }
      : { systemMessage: text.owner };
  process.stdout.write(JSON.stringify(out));
}

// Node resolves symlinks in import.meta.url, so resolve argv[1] the same way.
if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) main();
