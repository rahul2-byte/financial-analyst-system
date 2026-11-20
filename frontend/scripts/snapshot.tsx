/**
 * Screenshot harness. Renders the real <App/> against a scripted bridge
 * into a headless xterm, serializes the buffer to ANSI, and hands the ANSI to
 * `scripts/ts_tui_screenshot.py` for a PNG. No Python bridge, no network.
 *
 *   npm --prefix frontend run snapshot -- --all
 *   npm --prefix frontend run snapshot -- --scenario completed-hdfc
 *
 * Colour: build-snapshot.mjs sets FORCE_COLOR=3 before Ink loads, because the
 * harness stdout is not a real tty. SNAPSHOT_RAW_DIR=<dir> also writes each raw
 * byte stream Ink produced, for debugging.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import { SerializeAddon } from '@xterm/addon-serialize';
import React from 'react';

import { App } from '../src/ui/App.js';
import type { BridgeLaunch } from '../src/ui/hooks/useBridge.js';
import {
  flush,
  mount,
  ReplayBridge,
  sleep,
  type Replay,
} from '../test/support/term.js';

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..');
const GOLDENS = path.join(FRONTEND_ROOT, 'test', 'goldens');
const SNAPSHOT_DIR = path.join(FRONTEND_ROOT, 'dist', 'snapshots');
const PNG_DIR = path.join(REPO_ROOT, 'docs', 'design', 'screenshots');
const SCREENSHOT_SCRIPT = path.join(REPO_ROOT, 'scripts', 'ts_tui_screenshot.py');
const PYTHON = process.env.FINAI_PYTHON ?? path.join(REPO_ROOT, '.venv', 'bin', 'python');

type Step =
  | { readonly kind: 'type'; readonly text: string }
  | { readonly kind: 'enter' }
  | { readonly kind: 'ctrl-o' }
  | { readonly kind: 'wait'; readonly ms: number };

interface Scenario {
  readonly name: string;
  readonly cols: number;
  readonly rows: number;
  readonly steps: readonly Step[];
  readonly replay?: Replay;
  readonly sessions?: boolean;
  /** Time to wait after the keystrokes before capturing. */
  readonly settleMs?: number;
}

const SCENARIOS: readonly Scenario[] = [
  { name: 'idle', cols: 100, rows: 26, steps: [] },
  {
    // Paused mid-tools: the first tool is running, so the live region shows its label.
    name: 'running',
    cols: 100,
    rows: 26,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'hdfc_run.json', limit: 5, finish: false, delayMs: 250 },
    settleMs: 1700,
  },
  {
    name: 'streaming',
    cols: 100,
    rows: 30,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'hdfc_run.json', limit: 19, finish: false },
  },
  {
    name: 'completed-hdfc',
    cols: 100,
    rows: 34,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'hdfc_run.json', finish: true },
  },
  {
    name: 'clarification',
    cols: 100,
    rows: 26,
    steps: [{ kind: 'type', text: 'bank' }, { kind: 'enter' }],
    replay: { golden: 'clarification.json', finish: true },
  },
  {
    name: 'provider-error',
    cols: 100,
    rows: 26,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'provider_retry_then_failure.json', finish: true },
  },
  {
    name: 'cancelled',
    cols: 100,
    rows: 26,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'cancelled.json', finish: true },
  },
  {
    name: 'session-picker',
    cols: 100,
    rows: 22,
    steps: [{ kind: 'type', text: '/sessions' }, { kind: 'enter' }],
    sessions: true,
  },
  {
    name: 'help',
    cols: 100,
    rows: 30,
    steps: [{ kind: 'type', text: '/help' }, { kind: 'enter' }],
  },
  {
    name: 'narrow-80col',
    cols: 80,
    rows: 34,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'hdfc_run.json', finish: true },
  },
  {
    name: 'report-full',
    cols: 120,
    rows: 50,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'reports/report-full.json', finish: true },
  },
  {
    name: 'report-partial',
    cols: 100,
    rows: 50,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'reports/report-partial.json', finish: true },
  },
  {
    name: 'report-80col',
    cols: 80,
    rows: 50,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'reports/report-full.json', finish: true },
  },
  {
    name: 'lookup',
    cols: 100,
    rows: 30,
    steps: [{ kind: 'type', text: 'HDFCBANK' }, { kind: 'enter' }],
    replay: { golden: 'reports/report-lookup.json', finish: true },
  },
  {
    // Run finishes, then Ctrl+O at the idle prompt expands the last run's activity trail.
    name: 'ctrl-o-last-run',
    cols: 100,
    rows: 40,
    steps: [
      { kind: 'type', text: 'HDFCBANK' },
      { kind: 'enter' },
      { kind: 'wait', ms: 500 },
      { kind: 'ctrl-o' },
    ],
    replay: { golden: 'hdfc_run.json', finish: true },
  },
];

const SESSIONS = [
  { id: '0f3a9c21-7b1e-4d2a-9e44-1a2b3c4d5e6f', title: 'HDFC Bank review', message_count: 6, run_count: 2 },
  { id: '5b7e1d90-2c3a-4f5b-8a6d-9e0f1a2b3c4d', title: 'Tata Motors notes', message_count: 2, run_count: 1 },
];

const RAW_ID = /\b[a-z_]+:[a-z0-9_]+\b/;
const ANSI_SEQ = /\x1b\[[0-9;]*[A-Za-z]/g;

/** Fail the run when a snapshot leaks a raw tool id or overflows its width. */
function checkSnapshot(scenario: Scenario, ansi: string): void {
  const lines = ansi.replace(ANSI_SEQ, '').split(/\r?\n/);
  for (const line of lines) {
    if (RAW_ID.test(line)) throw new Error(`${scenario.name}: raw id in "${line}"`);
    if ([...line].length > scenario.cols) throw new Error(`${scenario.name}: line wider than ${scenario.cols}: "${line}"`);
  }
}

async function captureScenario(scenario: Scenario): Promise<string> {
  const bridge = new ReplayBridge(scenario.replay, GOLDENS);
  if (scenario.sessions) {
    bridge.setResult('session.list', { sessions: SESSIONS } as never);
  }

  const launch: BridgeLaunch = {
    repoRoot: REPO_ROOT,
    cwd: REPO_ROOT,
    dataDir: '.finai',
    columns: scenario.cols,
    rows: scenario.rows,
  };
  const { term, stdin, stdout, instance } = mount(
    React.createElement(App, { launch, injected: bridge }),
    scenario.cols,
    scenario.rows,
  );
  const serialize = new SerializeAddon();
  term.loadAddon(serialize);

  await sleep(200);
  for (const step of scenario.steps) {
    if (step.kind === 'wait') {
      await sleep(step.ms);
      continue;
    }
    stdin.send(step.kind === 'type' ? step.text : step.kind === 'ctrl-o' ? '\x0f' : '\r');
    await sleep(60);
  }
  await sleep(scenario.settleMs ?? 400);
  await flush(term);
  const ansi = serialize.serialize();
  checkSnapshot(scenario, ansi);
  if (process.env.SNAPSHOT_RAW_DIR) {
    mkdirSync(process.env.SNAPSHOT_RAW_DIR, { recursive: true });
    writeFileSync(path.join(process.env.SNAPSHOT_RAW_DIR, `${scenario.name}.raw`), stdout.raw.join(''), 'utf8');
  }
  instance.unmount();
  await instance.waitUntilExit().catch(() => undefined);
  bridge.close();
  term.dispose();
  return ansi;
}

function convert(name: string, ansiPath: string, cols: number): string {
  const pngPath = path.join(PNG_DIR, `ts-${name}.png`);
  mkdirSync(PNG_DIR, { recursive: true });
  const result = spawnSync(PYTHON, [SCREENSHOT_SCRIPT, ansiPath, pngPath, '--cols', String(cols), '--title', `FIN-AI ${name}`], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error(`screenshot ${name} failed: ${result.stderr || result.stdout}`);
  }
  return pngPath;
}

function selectScenarios(argv: readonly string[]): Scenario[] {
  if (argv.includes('--all')) return [...SCENARIOS];
  const index = argv.indexOf('--scenario');
  const name = index >= 0 ? argv[index + 1] : undefined;
  const found = SCENARIOS.find((scenario) => scenario.name === name);
  if (!found) {
    const names = SCENARIOS.map((scenario) => scenario.name).join(', ');
    throw new Error(`usage: snapshot --all | --scenario <name> (one of: ${names})`);
  }
  return [found];
}

async function main(): Promise<void> {
  const scenarios = selectScenarios(process.argv.slice(2));
  mkdirSync(SNAPSHOT_DIR, { recursive: true });
  for (const scenario of scenarios) {
    const ansi = await captureScenario(scenario);
    const ansiPath = path.join(SNAPSHOT_DIR, `${scenario.name}.ans`);
    writeFileSync(ansiPath, ansi, 'utf8');
    const png = convert(scenario.name, ansiPath, scenario.cols);
    process.stdout.write(`${scenario.name}\t${png}\n`);
  }
  process.exit(0);
}

main().catch((error: unknown) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
