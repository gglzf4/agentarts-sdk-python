// Node hook script tests — uses node:test + a file-based fetch stub preload.
import { test } from "node:test";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { pathToFileURL } from "node:url";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import assert from "node:assert/strict";

const here = fileURLToPath(import.meta.url);
const path = await import("node:path");
// tests/unit/toolkit/plugins/memory/code_agent/ → 7× .. → repo root → src/.../resources
const PLUGIN_ROOT = path.resolve(here, "..", "..", "..", "..", "..", "..", "..", "src", "agentarts", "toolkit", "plugins", "memory", "resources");
const SCRIPTS = path.join(PLUGIN_ROOT, "scripts");
const join = path.join;

function runHook(scriptName, stdinObj, env = {}) {
  const r = spawnSync(process.execPath, [join(SCRIPTS, scriptName)], {
    input: stdinObj ? JSON.stringify(stdinObj) : "",
    env: { ...process.env, ...env },
    encoding: "utf8",
    timeout: 10000,
  });
  return { stdout: r.stdout, stderr: r.stderr, code: r.status };
}

// Write a preload .mjs that patches globalThis.fetch with canned responses.
function writeFetchStubPreload(routes) {
  const dir = mkdtempSync(join(tmpdir(), "fetch-stub-"));
  const file = join(dir, "preload.mjs");
  const code = [
    "globalThis.__stubRoutes = " + JSON.stringify(routes) + ";",
    "globalThis.fetch = async (urlStr) => {",
    "  const u = new URL(urlStr);",
    "  const key = u.pathname;",
    "  let body = globalThis.__stubRoutes[key];",
    "  if (!body) { for (const k of Object.keys(globalThis.__stubRoutes)) { if (key.startsWith(k)) { body = globalThis.__stubRoutes[k]; break; } } }",
    "  return { ok: true, json: async () => body || {} };",
    "};",
  ].join("\n") + "\n";
  writeFileSync(file, code);
  return file;
}

// ── _shared.mjs unit tests ────────────────────────────────────────
test("_shared.resolveProject uses explicit env override", async () => {
  const mod = await import(join(SCRIPTS, "_shared.mjs") + "?t=" + Date.now());
  process.env.AGENTARTS_MEMORY_PROJECT_NAME = "my-proj";
  assert.equal(mod.resolveProject("/some/cwd"), "my-proj");
  delete process.env.AGENTARTS_MEMORY_PROJECT_NAME;
});

test("_shared.formatOutput returns text for plain platform", async () => {
  const mod = await import(join(SCRIPTS, "_shared.mjs") + "?t=" + (Date.now() + 1));
  assert.equal(mod.formatOutput("hello", "userPromptSubmit"), "hello");
  assert.equal(mod.formatOutput("", "x"), "");
});

test("_shared.coerceText handles string and array", async () => {
  const mod = await import(join(SCRIPTS, "_shared.mjs") + "?t=" + (Date.now() + 2));
  assert.equal(mod.coerceText("abc"), "abc");
  assert.equal(mod.coerceText([{ text: "a" }, "b"]), "a b");
  assert.equal(mod.coerceText(""), "");
});

// ── _shared.mjs platform detection ────────────────────────────────
function importDefaultUserId(env) {
  const modUrl = pathToFileURL(join(SCRIPTS, "_shared.mjs")).href + "?t=" + Date.now();
  const r = spawnSync(process.execPath, ["-e",
    `import(${JSON.stringify(modUrl)}).then(m => console.log(m.DEFAULT_USER_ID))`,
  ], {
    env: { ...process.env, ...env },
    encoding: "utf8",
    timeout: 5000,
  });
  return r.stdout.trim();
}

test("_shared: AGENTARTS_MEMORY_PLATFORM=codex yields codex-user", () => {
  assert.equal(importDefaultUserId({ AGENTARTS_MEMORY_PLATFORM: "codex" }), "codex-user");
});

test("_shared: AGENTARTS_MEMORY_PLATFORM=claude-code yields cc-user", () => {
  assert.equal(importDefaultUserId({ AGENTARTS_MEMORY_PLATFORM: "claude-code" }), "cc-user");
});

test("_shared: AGENTARTS_MEMORY_USER_ID overrides platform default", () => {
  assert.equal(
    importDefaultUserId({ AGENTARTS_MEMORY_PLATFORM: "codex", AGENTARTS_MEMORY_USER_ID: "zrm" }),
    "zrm",
  );
});

test("_shared: no platform env yields __default__", () => {
  assert.equal(importDefaultUserId({
    AGENTARTS_MEMORY_PLATFORM: "",
    CLAUDE_PLUGIN_ROOT: "",
    CODEX_PLUGIN_ROOT: "",
    OPENCODE_PLUGIN_ROOT: "",
  }), "__default__");
});

// ── session-start.mjs ─────────────────────────────────────────────
test("session-start drains stdin and exits 0 (no server)", () => {
  const r = runHook("session-start.mjs", { cwd: "/tmp" }, {
    AGENTARTS_MEMORY_SERVER_URL: "http://127.0.0.1:65535",
  });
  assert.equal(r.code, 0, "stderr: " + r.stderr);
  assert.equal(r.stdout, "");
});

// ── prompt-submit.mjs ─────────────────────────────────────────────
test("prompt-submit with no server produces no stdout", () => {
  const r = runHook(
    "prompt-submit.mjs",
    { cwd: "/tmp", prompt: "hello world" },
    { AGENTARTS_MEMORY_SERVER_URL: "http://127.0.0.1:65535" },
  );
  assert.equal(r.stdout, "");
});

test("prompt-submit with invalid JSON exits cleanly", () => {
  const r = spawnSync(process.execPath, [join(SCRIPTS, "prompt-submit.mjs")], {
    input: "not json",
    env: { ...process.env, AGENTARTS_MEMORY_SERVER_URL: "http://127.0.0.1:65535" },
    encoding: "utf8",
    timeout: 10000,
  });
  assert.equal(r.status, 0);
  assert.equal(r.stdout, "");
});

test("prompt-submit injects memory context with stubbed fetch", () => {
  const preload = writeFetchStubPreload({
    "/health": { status: "healthy" },
    "/search_memory/": {
      results: [{ content: "likes python", score: 0.9, type: "semantic" }],
    },
    "/search_summary/": { results: [] },
    "/add_messages/": {},
  });
  const r = spawnSync(process.execPath, ["--import", preload, join(SCRIPTS, "prompt-submit.mjs")], {
    input: JSON.stringify({ cwd: "/tmp", prompt: "python" }),
    env: { ...process.env, AGENTARTS_MEMORY_SERVER_URL: "http://stub.local" },
    encoding: "utf8",
    timeout: 10000,
  });
  assert.ok(r.stdout.includes("Related Memories"), "stdout: " + r.stdout + " stderr: " + r.stderr);
  assert.ok(r.stdout.includes("likes python"));
  assert.ok(r.stdout.includes("semantic"));
});

// ── pre-compact.mjs ───────────────────────────────────────────────
test("pre-compact with no server produces no stdout", () => {
  const r = runHook(
    "pre-compact.mjs",
    { cwd: "/tmp", messages: [{ role: "user", content: "compress me" }] },
    { AGENTARTS_MEMORY_SERVER_URL: "http://127.0.0.1:65535" },
  );
  assert.equal(r.stdout, "");
});

test("pre-compact exits 0 with valid input", () => {
  const r = runHook(
    "pre-compact.mjs",
    { cwd: "/tmp", messages: [] },
    { AGENTARTS_MEMORY_SERVER_URL: "http://127.0.0.1:65535" },
  );
  assert.equal(r.code, 0);
});

test("pre-compact injects memory with stubbed fetch", () => {
  const preload = writeFetchStubPreload({
    "/health": { status: "healthy" },
    "/search_memory/": {
      results: [{ content: "past decision", score: 0.8, type: "episodic" }],
    },
    "/search_summary/": { results: [] },
  });
  const r = spawnSync(process.execPath, ["--import", preload, join(SCRIPTS, "pre-compact.mjs")], {
    input: JSON.stringify({
      cwd: "/tmp",
      messages: [{ role: "user", content: "keep context" }],
    }),
    env: { ...process.env, AGENTARTS_MEMORY_SERVER_URL: "http://stub.local" },
    encoding: "utf8",
    timeout: 10000,
  });
  assert.ok(r.stdout.includes("Related Memories"), "stdout: " + r.stdout + " stderr: " + r.stderr);
  assert.ok(r.stdout.includes("past decision"));
});

// ── no-op scripts ─────────────────────────────────────────────────
const noOps = [
  "post-tool-use.mjs",
  "post-tool-failure.mjs",
  "pre-tool-use.mjs",
  "stop.mjs",
  "session-end.mjs",
  "subagent-start.mjs",
  "subagent-stop.mjs",
  "notification.mjs",
  "task-completed.mjs",
];
for (const name of noOps) {
  test("no-op " + name + " drains stdin and exits 0", () => {
    const r = runHook(name, { foo: "bar" });
    assert.equal(r.code, 0, "stderr: " + r.stderr);
    assert.equal(r.stdout, "");
  });
}
