#!/usr/bin/env node
// PreToolUse hook (Bash). `kit` is not on PATH: it runs from the kit checkout's
// own .venv as `uv run --project <kit checkout> kit <command>`. A Bash command
// that starts a bare `kit <subcommand>` (at the start, or after ; & | ( or a
// newline) is denied with the full command, so the agent retries at once
// instead of hitting exit 127 and searching the docs.
//
// The full command comes from <project>/.claude/kit.json `kit_command`, which
// `kit apply` records; without it the default checkout is named. Unreadable
// input allows the command and prints nothing.

import { readFileSync, realpathSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const KITFILE = ".claude/kit.json";
export const DEFAULT_COMMAND = "uv run --project ~/Projects/Personal/claude-kit kit";
const SUBCOMMANDS = ["apply", "bench", "status", "roadmap", "loop", "request", "insights"];
const BARE = new RegExp(`(^|[;&|(\\n])\\s*kit\\s+(${SUBCOMMANDS.join("|")})\\b`);

export function recordedCommand(projectDir) {
  try {
    const value = JSON.parse(readFileSync(join(projectDir, KITFILE), "utf8")).kit_command;
    return typeof value === "string" && value ? value : DEFAULT_COMMAND;
  } catch {
    return DEFAULT_COMMAND;
  }
}

export function decide(command, kitCommand) {
  if (!BARE.test(command)) return null;
  return {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason:
      `kit is not on PATH. Run it as \`${kitCommand} <command>\`, ` +
      `for example \`${kitCommand} roadmap .\`.`,
  };
}

function main() {
  let input;
  try {
    input = JSON.parse(readFileSync(0, "utf8"));
  } catch {
    return;
  }
  const command = input?.tool_input?.command;
  if (typeof command !== "string") return;
  const body = decide(command, recordedCommand(process.env.CLAUDE_PROJECT_DIR ?? ""));
  if (body) process.stdout.write(JSON.stringify({ hookSpecificOutput: body }));
}

// Node resolves symlinks in import.meta.url, so resolve argv[1] the same way.
if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) main();
