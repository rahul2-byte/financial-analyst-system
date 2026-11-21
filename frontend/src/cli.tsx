/**
 * Entry point for `node frontend/dist/cli.js`.
 *
 * Parses the arguments, refuses to run without a terminal, renders <App/> and
 * shuts the bridge down after Ink has restored the terminal.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import { render } from 'ink';

import { findRepoRoot } from './bridge/process.js';
import { MODES } from './commands/registry.js';
import { PROTOCOL_VERSION } from './protocol/version.js';
import { App } from './ui/App.js';
import { shutdownAllBridges, startFailure, type BridgeLaunch } from './ui/hooks/useBridge.js';

const USAGE = `usage: finai [--data-dir DIR] [--session ID] [--mode guided|review|autonomous]
             [--fake-events FILE] [--fake-delay-ms N] [--version] [--help]

Interactive FIN-AI terminal (TypeScript UI over the Python bridge).
One-shot queries and --plain/--json run through: python -m finai`;

const EXIT_USAGE = 2;
const EXIT_NO_TERMINAL = 1;
const SHUTDOWN_GUARD_MS = 6_000;

function fail(message: string, code: number): never {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

async function main(): Promise<void> {
  let parsed: ReturnType<typeof parseArgs<{
    options: {
      'data-dir': { type: 'string' };
      session: { type: 'string' };
      mode: { type: 'string' };
      'fake-events': { type: 'string' };
      'fake-delay-ms': { type: 'string' };
      help: { type: 'boolean'; short: 'h' };
      version: { type: 'boolean' };
    };
    allowPositionals: true;
  }>>;
  try {
    parsed = parseArgs({
      args: process.argv.slice(2),
      allowPositionals: true,
      strict: true,
      options: {
        'data-dir': { type: 'string' },
        session: { type: 'string' },
        mode: { type: 'string' },
        'fake-events': { type: 'string' },
        'fake-delay-ms': { type: 'string' },
        help: { type: 'boolean', short: 'h' },
        version: { type: 'boolean' },
      },
    });
  } catch (error) {
    fail(`finai: ${error instanceof Error ? error.message : String(error)}\n${USAGE}`, EXIT_USAGE);
  }

  const { values, positionals } = parsed;
  if (values.help) {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  }
  if (values.version) {
    process.stdout.write(`finai ui (protocol ${PROTOCOL_VERSION})\n`);
    process.exit(0);
  }
  if (positionals.length > 0) {
    fail('finai: one-shot queries run through python -m finai, this UI is interactive only.', EXIT_USAGE);
  }
  if (values.mode !== undefined && !(MODES as readonly string[]).includes(values.mode)) {
    fail(`finai: --mode must be one of ${MODES.join(', ')}`, EXIT_USAGE);
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    fail('finai: the terminal UI needs an interactive terminal (use: python -m finai --plain)', EXIT_NO_TERMINAL);
  }

  const here = path.dirname(fileURLToPath(import.meta.url));
  const launch: BridgeLaunch = {
    repoRoot: findRepoRoot(here),
    cwd: process.cwd(),
    dataDir: values['data-dir'],
    session: values.session,
    mode: values.mode,
    fakeEvents: values['fake-events'] === undefined ? undefined : path.resolve(values['fake-events']),
    fakeDelayMs: values['fake-delay-ms'] === undefined ? undefined : Number(values['fake-delay-ms']),
    columns: process.stdout.columns || 80,
    rows: process.stdout.rows || 24,
  };

  let signalCode = 0;
  const instance = render(<App launch={launch} />, { exitOnCtrlC: false, incrementalRendering: true });
  const onSignal = (code: number) => {
    signalCode = code;
    instance.unmount();
  };
  process.once('SIGINT', () => onSignal(130));
  process.once('SIGTERM', () => onSignal(143));
  process.once('uncaughtException', (error) => {
    instance.unmount();
    process.stderr.write(`finai: ${error.stack ?? error.message}\n`);
    process.exit(1);
  });

  await instance.waitUntilExit();

  // Ink has restored the terminal; now stop the backend.
  await Promise.race([
    shutdownAllBridges(),
    new Promise((resolve) => setTimeout(resolve, SHUTDOWN_GUARD_MS).unref()),
  ]);
  process.exit(startFailure.message !== null ? 1 : signalCode);
}

void main();
