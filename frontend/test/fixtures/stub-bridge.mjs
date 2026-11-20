#!/usr/bin/env node
// Minimal stand-in for `python -m finai.bridge`, used by test/process.test.ts
// until the real Python bridge server exists (P2b).
//
// Flags:
//   --crash-on-initialize   exit(3) when `initialize` arrives
//   --crash-immediately     exit(7) at startup
//   --ignore-shutdown       never answer `shutdown`; still dies on SIGTERM
//   --ignore-sigterm        ignore SIGTERM (needs SIGKILL); answers `shutdown` normally
//   --stderr-lines N        write N stderr lines at startup
import { createInterface } from 'node:readline';

const argv = process.argv.slice(2);
const has = (flag) => argv.includes(flag);
const valueOf = (flag) => {
  const index = argv.indexOf(flag);
  return index === -1 ? undefined : argv[index + 1];
};

const log = (line) => {
  process.stderr.write(`stub-bridge: ${line}\n`);
};

log(`started pid=${process.pid}`);

if (has('--crash-immediately')) {
  process.exit(7);
}

const stderrLineCount = Number(valueOf('--stderr-lines') ?? '0');
for (let i = 0; i < stderrLineCount; i += 1) log(`noise ${i + 1}`);

if (has('--ignore-sigterm')) {
  process.on('SIGTERM', () => {
    log('ignoring SIGTERM');
  });
}

const write = (message) => {
  process.stdout.write(`${JSON.stringify(message)}\n`);
};

const session = { id: 'stub-session', title: 'Stub session', message_count: 0, run_count: 0 };

const reader = createInterface({ input: process.stdin, crlfDelay: Infinity });
reader.on('line', (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    write({ jsonrpc: '2.0', id: 0, error: { code: -32700, message: 'parse error' } });
    return;
  }
  if (message.method === 'initialize') {
    log(`received initialize id=${message.id}`);
    if (has('--crash-on-initialize')) process.exit(3);
    write({
      jsonrpc: '2.0',
      id: message.id,
      result: {
        protocol_version: 1,
        server_version: 'stub-0.0.0',
        session,
        mode: 'guided',
        data_dir: '.finai',
        model: null,
      },
    });
    return;
  }
  if (message.method === 'shutdown') {
    log(`received shutdown id=${message.id}`);
    if (has('--ignore-shutdown')) return; // wait for SIGKILL
    write({ jsonrpc: '2.0', id: message.id, result: {} });
    setTimeout(() => process.exit(0), 10);
    return;
  }
  write({
    jsonrpc: '2.0',
    id: message.id,
    error: { code: -32601, message: `method not found: ${String(message.method)}` },
  });
});

reader.on('close', () => {
  log('stdin closed');
  process.exit(0);
});
