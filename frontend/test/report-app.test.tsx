/**
 * Plan U3/U1: the real <App/> committing the structured report at run.finished, the
 * clipped live draft, failure wording, the 256-colour fallback and NO_COLOR.
 */
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { Text } from 'ink';
import { render } from 'ink-testing-library';

import { App } from '../src/ui/App.js';
import { ClippedTail } from '../src/ui/ClippedTail.js';
import type { BridgeLaunch } from '../src/ui/hooks/useBridge.js';
import { color, nearest256, tokens } from '../src/render/theme.js';
import { describeFailure } from '../src/state/transcript.js';
import { RAW_ID } from './support/report.js';
import { flush, mount, ReplayBridge, sleep, terminalLines, type Mounted } from './support/term.js';

const COLS = 100;
const ROWS = 40;
const launch: BridgeLaunch = {
  repoRoot: '/nonexistent-repo',
  cwd: '/nonexistent-repo',
  dataDir: '.finai',
  columns: COLS,
  rows: ROWS,
};

let mounted: Mounted | null = null;
let bridge: ReplayBridge | null = null;
afterEach(() => {
  mounted?.instance.unmount();
  bridge?.close();
  mounted?.term.dispose();
  mounted = null;
  bridge = null;
});

async function until(term: Mounted['term'], check: (text: string[]) => boolean): Promise<string[]> {
  const deadline = Date.now() + 8000;
  for (;;) {
    await flush(term);
    const text = terminalLines(term);
    if (check(text)) return text;
    if (Date.now() > deadline) throw new Error(`timed out; buffer:\n${text.filter((l) => l.trim()).join('\n')}`);
    await sleep(25);
  }
}

async function runReplay(golden: string): Promise<string[]> {
  bridge = new ReplayBridge({ golden, finish: true });
  mounted = mount(<App launch={launch} injected={bridge} />, COLS, ROWS);
  const { term, stdin } = mounted;
  await until(term, (text) => text.some((line) => line.includes('FIN-AI')));
  stdin.send('HDFCBANK');
  await sleep(60);
  stdin.send('\r');
  return until(term, (text) => text.some((line) => /^(✓|◐ partial|✕ failed|· cancelled)/.test(line)));
}

describe('structured report in the App', () => {
  it('commits the report card once and a complete footer', async () => {
    const text = await runReplay('reports/report-full.json');
    expect(text.filter((l) => l.startsWith('╭─ HDFCBANK')).length).toBe(1);
    expect(text.some((l) => l.includes('Key figures'))).toBe(true);
    expect(text.some((l) => l.includes('┃ Final view'))).toBe(true);
    expect(text.filter((l) => l.startsWith('Sources')).length).toBe(0); // sources live inside the report, indented
    expect(text.filter((l) => /^ {2}Sources/.test(l)).length).toBe(1);
    expect(text.find((l) => l.startsWith('✓ '))).toMatch(/· \d+ tools? · 3 sources$/);
    for (const l of text) expect(l).not.toMatch(RAW_ID);
  });

  it('partial run: ◐ footer naming the unavailable source', async () => {
    const text = await runReplay('reports/report-partial.json');
    const footer = text.find((l) => l.startsWith('◐ partial'));
    expect(footer).toBeDefined();
    expect(footer).toContain('news unavailable');
  });

  it('lookup run: compact card, no signals block', async () => {
    const text = await runReplay('reports/report-lookup.json');
    expect(text.some((l) => l.startsWith('╭─ HDFCBANK'))).toBe(true);
    expect(text.some((l) => l.includes('Technical signals'))).toBe(false);
  });

  it('falls back to the markdown answer when no report is supplied', async () => {
    const text = await runReplay('hdfc_run.json');
    expect(text.some((l) => l.startsWith('╭─ '))).toBe(false);
    expect(text.some((l) => l.includes('Executive Summary'))).toBe(true);
  });
});

describe('ClippedTail', () => {
  it('shows only the last rows of a long draft and all of a short one', async () => {
    const long = Array.from({ length: 30 }, (_, i) => `line ${i + 1}`);
    const { lastFrame, rerender, unmount } = render(
      <ClippedTail maxRows={6}>
        {long.map((l) => (
          <Text key={l}>{l}</Text>
        ))}
      </ClippedTail>,
    );
    await sleep(60);
    rerender(
      <ClippedTail maxRows={6}>
        {long.map((l) => (
          <Text key={l}>{l}</Text>
        ))}
      </ClippedTail>,
    );
    await sleep(60);
    const frame = lastFrame() ?? '';
    expect(frame.split('\n').length).toBeLessThanOrEqual(6);
    expect(frame).toContain('line 30');
    expect(frame).not.toContain('line 1\n');
    unmount();

    const short = render(
      <ClippedTail maxRows={6}>
        <Text>only line</Text>
      </ClippedTail>,
    );
    await sleep(40);
    expect(short.lastFrame()).toBe('only line');
    short.unmount();
  });
});

describe('describeFailure', () => {
  it('maps provider errors to a reason and a next step, never a raw id', () => {
    expect(describeFailure(['429 rate limit exceeded for llm:openai']).notice).toMatch(/rate limit.*\./i);
    expect(describeFailure(['insufficient_quota']).notice).toMatch(/quota/i);
    const unknown = describeFailure(['Something odd happened']);
    expect(unknown.notice).toBe('Something odd happened. Try /retry.');
    expect(describeFailure([]).reason).toBe('The run did not finish');
  });
});

describe('colour tokens', () => {
  const saved = { ...process.env };
  afterEach(() => {
    process.env = { ...saved };
  });

  it('truecolor uses hex, 256-colour fallback uses ansi256(n)', () => {
    delete process.env.NO_COLOR;
    process.env.COLORTERM = 'truecolor';
    expect(color('ledger')).toBe(tokens.ledger);
    process.env.COLORTERM = '';
    expect(color('ledger')).toMatch(/^ansi256\(\d+\)$/);
  });

  it('NO_COLOR removes every colour', () => {
    process.env.NO_COLOR = '1';
    for (const key of Object.keys(tokens) as Array<keyof typeof tokens>) expect(color(key)).toBeUndefined();
  });

  it('nearest256 picks cube corners and the grey ramp', () => {
    expect(nearest256('#000000')).toBe(16);
    expect(nearest256('#ffffff')).toBe(231);
    expect(nearest256('#808080')).toBeGreaterThanOrEqual(232);
    expect(nearest256('#ff0000')).toBe(196);
  });
});

describe('NO_COLOR', () => {
  it('emits no SGR colour sequences for a full report', async () => {
    const saved = process.env.NO_COLOR;
    process.env.NO_COLOR = '1';
    try {
      await runReplay('reports/report-full.json');
      const raw = mounted?.stdout.raw.join('') ?? '';
      expect(raw).toContain('Key figures');
      // 30-37, 38;..., 40-47, 48;..., 90-97, 100-107 are colours; bold/dim/reset are allowed.
      expect(raw).not.toMatch(/\x1b\[(?:[0-9;]*;)?(?:3[0-8]|4[0-8]|9[0-7]|10[0-7])(?:;[0-9;]*)?m/);
    } finally {
      if (saved === undefined) delete process.env.NO_COLOR;
      else process.env.NO_COLOR = saved;
    }
  });
});

describe('Ctrl+O at idle', () => {
  it('expands the last run with human-labelled tool rows', async () => {
    await runReplay('hdfc_run.json');
    mounted?.stdin.send('\x0f');
    const text = await until(mounted!.term, (t) => t.filter((l) => l.startsWith('⏺ Gathered evidence')).length >= 2);
    expect(text.filter((l) => l.includes('⎿')).length).toBeGreaterThanOrEqual(3);
    for (const l of text) expect(l).not.toMatch(RAW_ID);
  });
});
