#!/usr/bin/env node
// session-end — no-op placeholder. Drains stdin, does nothing.
async function main() {
  for await (const _ of process.stdin) { /* drain */ }
}
main();
