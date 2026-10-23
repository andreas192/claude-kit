#!/usr/bin/env node
// PreToolUse hook (Write|Edit). Enforces the repo's code conventions at the
// moment a test file is written, so the rule reaches every model regardless
// of what it read earlier. The rules come from <project>/.claude/test-layers.json:
//
//   { "pipeline_test": "tests/test_cli_pipeline.py", "package": "dgi",
//     "wiring_modules": ["cli", "pipeline"], "wiring_functions": ["run_refresh"],
//     "conventions_doc": "docs/code-conventions.md" }
//
//  - Denies wiring tests (CliRunner, the wiring functions, the wiring modules)
//    in any test file beside the pipeline test: wiring has no unit spec, logic
//    gets a UNIT test.
//  - Injects a pointer to the PIPELINE-layer contract when the pipeline test is touched.
//
// A missing or malformed config, or unreadable input, allows the write and
// prints nothing: the guard must never block an edit because of its own setup.

import { readFileSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

const CONFIG_PATH = ".claude/test-layers.json";

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function buildRules(config) {
  const { pipeline_test: pipelineTest, package: pkg, wiring_modules: modules, wiring_functions: functions } = config;
  const mods = modules.map(escape).join("|");
  const wiring = [
    "\\bCliRunner\\b",
    ...functions.map((fn) => `\\b${escape(fn)}\\s*\\(`),
    `from ${escape(pkg)}\\.(${mods}) import`,
    `import ${escape(pkg)}\\.(${mods})\\b`,
    `from ${escape(pkg)} import (${mods})\\b`,
  ].join("|");
  return {
    pipelineTest: new RegExp(`(^|/)${escape(pipelineTest)}$`),
    anyTest: new RegExp(`(^|/)${escape(dirname(pipelineTest))}/[^/]+\\.py$`),
    wiring: new RegExp(wiring),
  };
}

export function decide(rules, file, text, doc) {
  if (rules.pipelineTest.test(file)) {
    return {
      hookEventName: "PreToolUse",
      additionalContext:
        `Follow ${doc} section 3, PIPELINE layer: happy path, idempotence, at most one clean-failure per command. ` +
        "No data-level cases; those belong in the function's UNIT test.",
    };
  }
  if (rules.anyTest.test(file) && rules.wiring.test(text)) {
    return {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason:
        `${doc}: cli.py and pipeline.py are wiring and get no unit spec. ` +
        "Test the function directly in a UNIT test beside its module's tests.",
    };
  }
  return null;
}

const isStrings = (v) => Array.isArray(v) && v.every((x) => typeof x === "string");

function validConfig(config) {
  return (
    typeof config?.pipeline_test === "string" &&
    typeof config.package === "string" &&
    typeof config.conventions_doc === "string" &&
    isStrings(config.wiring_modules) &&
    config.wiring_modules.length > 0 &&
    isStrings(config.wiring_functions)
  );
}

function main() {
  let config;
  let input;
  try {
    config = JSON.parse(readFileSync(join(process.env.CLAUDE_PROJECT_DIR ?? "", CONFIG_PATH), "utf8"));
    if (!validConfig(config)) return;
    input = JSON.parse(readFileSync(0, "utf8"));
  } catch {
    return;
  }
  const file = input?.tool_input?.file_path ?? "";
  const text = input?.tool_input?.content ?? input?.tool_input?.new_string ?? "";
  const body = decide(buildRules(config), file, text, config.conventions_doc);
  if (body) process.stdout.write(JSON.stringify({ hookSpecificOutput: body }));
}

// Node resolves symlinks in import.meta.url, so resolve argv[1] the same way.
if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) main();
