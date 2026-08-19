#!/usr/bin/env node
// SessionStart — probe server health only. No memory search here.
import { healthCheck, isSdkChildContext } from "./_shared.mjs";

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }
  if (isSdkChildContext(data)) return;

  await healthCheck();
  setTimeout(() => process.exit(0), 300).unref();
}

main();
