// agentarts-memory-code_agent — shared utilities for hook scripts.
//
// All hook scripts import from this module for:
//   - REST URL / timeout config
//   - resolveProject(cwd) — git toplevel basename for scope isolation
//   - addMessages() / searchAndFormat() / healthCheck() — HTTP calls
//   - platform detection (Claude Code vs Codex vs Cursor)
//   - output formatting

import { execSync } from "node:child_process";
import { basename } from "node:path";

// ---------------------------------------------------------------------------
// Version
// ---------------------------------------------------------------------------
export const PLUGIN_VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// Platform detection
//
// Claude Code sets CLAUDE_PLUGIN_ROOT; Codex sets CODEX_PLUGIN_ROOT.
// OpenCode sets OPENCODE_PLUGIN_ROOT.
// Used to derive a per-platform default user_id.
// ---------------------------------------------------------------------------
export function detectPlatform() {
  if (process.env.AGENTARTS_MEMORY_PLATFORM) return process.env.AGENTARTS_MEMORY_PLATFORM;
  if (process.env.CLAUDE_PLUGIN_ROOT) return "claude-code";
  if (process.env.CODEX_PLUGIN_ROOT) return "codex";
  if (process.env.OPENCODE_PLUGIN_ROOT) return "opencode";
  return "unknown";
}

const PLATFORM_USER_ID = {
  "claude-code": "cc-user",
  "codex": "codex-user",
  "opencode": "opencode-user",
  "unknown": "__default__",
};

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
export const REST_URL =
  process.env.AGENTARTS_MEMORY_SERVER_URL || "http://127.0.0.1:8719";
export const DEBUG = process.env.AGENTARTS_MEMORY_DEBUG === "1";

// Default user_id from environment or platform detection
export const DEFAULT_USER_ID =
  process.env.AGENTARTS_MEMORY_USER_ID || PLATFORM_USER_ID[detectPlatform()];

/**
 * Resolve user_id with priority:
 *   1. AGENTARTS_MEMORY_USER_ID env var (explicit override)
 *   2. payload.user_id / payload.userId (from hook request)
 *   3. Platform-based default (cc-user / codex-user / __default__)
 */
export function resolveUserId(payload) {
  if (process.env.AGENTARTS_MEMORY_USER_ID) return process.env.AGENTARTS_MEMORY_USER_ID;
  if (payload && typeof payload === "object") {
    const explicit = payload.user_id || payload.userId;
    if (explicit && typeof explicit === "string" && explicit.trim()) {
      return explicit.trim();
    }
  }
  return DEFAULT_USER_ID;
}

export const SEARCH_MEM_NUM = 5;
export const SEARCH_SUMMARY_NUM = 3;
export const DEFAULT_THRESHOLD = 0.3;
export const MAX_TRUNCATE = 8000;

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------
export function authHeaders() {
  return { "Content-Type": "application/json" };
}

export async function post(path, body, timeoutMs = 3000) {
  try {
    const res = await fetch(`${REST_URL}/${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (DEBUG && !res.ok) console.error(`[agentarts] POST /${path} returned ${res.status}`);
  } catch (e) {
    if (DEBUG) console.error(`[agentarts] POST /${path} failed:`, e?.message || e);
  }
}

export async function postJson(path, body, timeoutMs = 0) {
  try {
    const opts = {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    };
    if (timeoutMs > 0) opts.signal = AbortSignal.timeout(timeoutMs);
    const res = await fetch(`${REST_URL}/${path}`, opts);
    if (res.ok) return await res.json();
    if (DEBUG) console.error(`[agentarts] POST /${path} returned ${res.status}`);
  } catch (e) {
    if (DEBUG) console.error(`[agentarts] POST /${path} (json) failed:`, e?.message || e);
  }
  return null;
}

export async function getJson(path, timeoutMs = 800) {
  try {
    const res = await fetch(`${REST_URL}/${path}`, {
      method: "GET",
      headers: authHeaders(),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (res.ok) return await res.json();
  } catch {
    // ignore
  }
  return null;
}

// ---------------------------------------------------------------------------
// Endpoints (trailing slash matches FastAPI route declarations)
// ---------------------------------------------------------------------------
const EP_ADD_MESSAGES = "add_messages/";
const EP_SEARCH_MEMORY = "search_memory/";
const EP_SEARCH_SUMMARY = "search_summary/";
const EP_HEALTH = "health";

// ---------------------------------------------------------------------------
// Project resolution — scope_id = project basename for per-project isolation.
// ---------------------------------------------------------------------------
export function resolveProject(cwd) {
  const explicit = process.env.AGENTARTS_MEMORY_PROJECT_NAME;
  if (explicit && explicit.trim()) return explicit.trim();
  const dir = cwd && cwd.trim() ? cwd : process.cwd();
  try {
    const top = execSync("git rev-parse --show-toplevel", {
      cwd: dir,
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 500,
    }).toString().trim();
    if (top) return basename(top);
  } catch {}
  return basename(dir);
}

// ---------------------------------------------------------------------------
// High-level operations
// ---------------------------------------------------------------------------
export async function addMessages(messages, scopeId, userId = DEFAULT_USER_ID) {
  await post(EP_ADD_MESSAGES, {
    messages,
    user_id: userId,
    scope_id: scopeId,
    plugin_version: PLUGIN_VERSION,
  }, 3000);
}

/**
 * Combined search — calls /search_memory/ and /search_summary/, merges into a
 * formatted context string for stdout injection.
 */
export async function searchAndFormat(query, scopeId, userId = DEFAULT_USER_ID) {
  const [memResult, summaryResult] = await Promise.all([
    postJson(EP_SEARCH_MEMORY, {
      query,
      num: SEARCH_MEM_NUM,
      user_id: userId,
      scope_id: scopeId,
      threshold: DEFAULT_THRESHOLD,
      plugin_version: PLUGIN_VERSION,
    }),
    postJson(EP_SEARCH_SUMMARY, {
      query,
      num: SEARCH_SUMMARY_NUM,
      user_id: userId,
      scope_id: scopeId,
      threshold: DEFAULT_THRESHOLD,
      plugin_version: PLUGIN_VERSION,
    }),
  ]);

  const memItems = memResult?.results || [];
  const summaryItems = summaryResult?.results || [];
  const lines = [];

  if (memItems.length) {
    lines.push("## Related Memories");
    for (const r of memItems) {
      const label = r.type ? `[${r.type}]` : "";
      const content = String(r.content || "").slice(0, 300);
      const score = Number(r.score || 0).toFixed(2);
      lines.push(`- ${label} ${content} (score: ${score})`);
    }
  }
  if (summaryItems.length) {
    if (lines.length) lines.push("");
    lines.push("## Related History Summaries");
    for (const r of summaryItems) {
      const content = String(r.content || "").slice(0, 300);
      const score = Number(r.score || 0).toFixed(2);
      lines.push(`- ${content} (score: ${score})`);
    }
  }
  return lines.join("\n");
}

export async function healthCheck() {
  const r = await getJson(EP_HEALTH, 800);
  return r && r.status === "healthy";
}

// ---------------------------------------------------------------------------
// SDK child guard — prevents sub-agents from double-capturing.
// ---------------------------------------------------------------------------
export function isSdkChildContext(payload) {
  if (process.env.AGENTARTS_SDK_CHILD === "1") return true;
  if (!payload || typeof payload !== "object") return false;
  return payload.entrypoint === "sdk-ts";
}

// ---------------------------------------------------------------------------
// Output format — Claude Code / Codex: stdout is plain text.
// (Cursor JSON support omitted this round; kept extensible.)
// ---------------------------------------------------------------------------
export function formatOutput(text, eventType = "generic") {
  return text || "";
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------
export function truncate(value, max = MAX_TRUNCATE) {
  if (typeof value === "string" && value.length > max) return value.slice(0, max) + "\n[...truncated]";
  return value;
}

export function coerceText(content) {
  if (!content) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((b) => (typeof b === "string" ? b : b?.text || b?.content || ""))
      .filter(Boolean)
      .join(" ");
  }
  return String(content);
}
