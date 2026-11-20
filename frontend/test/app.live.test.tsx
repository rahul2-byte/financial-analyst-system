/**
 * Regression: the live region must not duplicate in a real terminal buffer, and the
 * running tool label must reach the screen. Renders the real <App/> through Ink into
 * @xterm/headless and reads the buffer (scrollback included), not Ink's last frame.
 */
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { App } from '../src/ui/App.js';
import type { BridgeLaunch } from '../src/ui/hooks/useBridge.js';
import { SPINNER_FRAMES } from '../src/render/format.js';
import { flush, mount, ReplayBridge, sleep, terminalLines, type Mounted } from './support/term.js';

const COLS = 100;
const ROWS = 26;
const launch: BridgeLaunch = {
  repoRoot: '/nonexistent-repo',
  cwd: '/nonexistent-repo',
  dataDir: '.finai',
  columns: COLS,
  rows: ROWS,
};

const RULE = /^─{20,}$/;

let mounted: Mounted | null = null;
let bridge: ReplayBridge | null = null;

afterEach(() => {
  mounted?.instance.unmount();
  bridge?.close();
  mounted?.term.dispose();
  mounted = null;
  bridge = null;
});

/** Let xterm parse everything Ink wrote, then read every line of the buffer. */
async function lines(term: Mounted['term']): Promise<string[]> {
  await flush(term);
  return terminalLines(term);
}

async function until(term: Mounted['term'], check: (text: string[]) => boolean): Promise<string[]> {
  const deadline = Date.now() + 8000;
  for (;;) {
    const text = await lines(term);
    if (check(text)) return text;
    if (Date.now() > deadline) throw new Error(`timed out; buffer:\n${text.filter((l) => l.trim()).join('\n')}`);
    await sleep(25);
  }
}

const count = (text: string[], predicate: (line: string) => boolean): number => text.filter(predicate).length;
const isSpinnerLine = (line: string): boolean => SPINNER_FRAMES.some((frame) => line.startsWith(`${frame} `));

describe('live region in a terminal buffer', () => {
  it('shows one spinner line and one composer rule while a tool runs', async () => {
    bridge = new ReplayBridge({ golden: 'hdfc_run.json', limit: 5, finish: false, delayMs: 60 });
    mounted = mount(<App launch={launch} injected={bridge} />, COLS, ROWS);
    const { term, stdin } = mounted;

    await until(term, (text) => text.some((line) => line.includes('FIN-AI')));
    stdin.send('HDFCBANK');
    await sleep(60);
    stdin.send('\r');

    // The tool is still running at event 5, so its display label must be on screen.
    const running = await until(term, (text) => text.some((line) => line.includes('Fetching fundamentals')));
    expect(count(running, isSpinnerLine)).toBe(1);
    expect(count(running, (line) => RULE.test(line))).toBe(1);

    // Let the spinner advance and the buffer settle; still exactly one live spinner line.
    await sleep(400);
    const later = await lines(term);
    expect(count(later, isSpinnerLine)).toBe(1);
    expect(count(later, (line) => RULE.test(line))).toBe(1);
  });

  it('leaves each committed item once in scrollback after the run finishes', async () => {
    bridge = new ReplayBridge({ golden: 'hdfc_run.json', finish: true });
    mounted = mount(<App launch={launch} injected={bridge} />, COLS, ROWS);
    const { term, stdin } = mounted;

    await until(term, (text) => text.some((line) => line.includes('FIN-AI')));
    stdin.send('HDFCBANK');
    await sleep(60);
    stdin.send('\r');

    const done = await until(term, (text) => text.some((line) => line.startsWith('✓ ')));
    expect(count(done, (line) => line.includes('FIN-AI'))).toBe(1);
    expect(count(done, (line) => line.startsWith('› HDFCBANK'))).toBe(1);
    expect(count(done, isSpinnerLine)).toBe(0);
    expect(count(done, (line) => line.startsWith('✓ '))).toBe(1);
    expect(count(done, (line) => line.includes('Executive Summary'))).toBe(1);
    // The header keeps a gap between the FIN-AI ledger and the session subtitle.
    expect(count(done, (line) => /^FIN-AI {2,}\S/.test(line))).toBe(1);
  });
});
