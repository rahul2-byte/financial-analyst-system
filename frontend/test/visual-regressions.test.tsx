/**
 * Visual regressions from the round-2 screenshot review: sibling segments keep their
 * gaps, markdown tables are box-aligned on every row, and bold/code spans add no spaces.
 */
import { describe, expect, it } from 'vitest';
import { render } from 'ink-testing-library';
import type { ReactElement } from 'react';
import { Clarification } from '../src/ui/Clarification.js';
import { Header } from '../src/ui/Header.js';
import { LiveActivity } from '../src/ui/LiveActivity.js';
import { Notice } from '../src/ui/Notice.js';
import { RunFooter } from '../src/ui/RunFooter.js';
import { Sources } from '../src/ui/Sources.js';
import { render as renderMarkdown } from '../src/render/markdown.js';
import { displayWidth } from '../src/render/format.js';
import type { ActivityState } from '../src/state/types.js';
import type { DisplaySource } from '../src/protocol/generated.js';

const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;

function frameOf(element: ReactElement): string {
  const { lastFrame, unmount } = render(element);
  const frame = (lastFrame() ?? '').replace(ANSI, '');
  unmount();
  return frame;
}

function activity(label: string, status: ActivityState['status']): ActivityState {
  return { label, status, detail: null };
}

const TABLE_CHARS = new Set(['┌', '┬', '┐', '│', '├', '┼', '┤', '└', '┴', '┘']);

/** Display columns of every box character on a line. */
function barColumns(line: string): number[] {
  const columns: number[] = [];
  const chars = Array.from(line);
  chars.forEach((char, index) => {
    if (TABLE_CHARS.has(char)) columns.push(displayWidth(chars.slice(0, index).join('')));
  });
  return columns;
}

function tableLines(frame: string): string[] {
  return frame.split('\n').filter((line) => /^[┌├└│]/.test(line));
}

describe('sibling segments keep their gaps', () => {
  it('Sources: "1. Upstox · api.upstox.com"', () => {
    const sources = [{ label: 'Upstox', host: 'api.upstox.com', url: 'https://api.upstox.com' }] as DisplaySource[];
    const frame = frameOf(<Sources sources={sources} width={60} />);
    expect(frame).toContain('Sources');
    expect(frame).toContain('1. Upstox · api.upstox.com');
  });

  it('Sources: no host means no separator', () => {
    const sources = [{ label: 'Upstox', url: 'https://api.upstox.com' }] as DisplaySource[];
    expect(frameOf(<Sources sources={sources} width={60} />)).toContain('1. Upstox');
  });

  it('LiveActivity: spinner line has two spaces before the elapsed time', () => {
    const frame = frameOf(
      <LiveActivity
        frame={0}
        operation="Fetching fundamentals"
        elapsedSeconds={1}
        activeTools={[]}
        width={60}
      />,
    );
    expect(frame).toBe('⠋ Fetching fundamentals  1s');
  });

  it('LiveActivity: one active tool shows once (spinner line only)', () => {
    const frame = frameOf(
      <LiveActivity
        frame={0}
        operation="Fetching fundamentals"
        elapsedSeconds={1}
        activeTools={['data:fetch_fundamentals']}
        activities={{ 'tool:data:fetch_fundamentals': activity('Fetching fundamentals', 'running') }}
        width={60}
      />,
    );
    expect(frame.split('Fetching fundamentals')).toHaveLength(2);
    expect(frame).not.toContain('⎿');
  });

  it('LiveActivity: other active tools keep their tree line', () => {
    const frame = frameOf(
      <LiveActivity
        frame={0}
        operation="Fetching fundamentals"
        elapsedSeconds={1}
        activeTools={['data:fetch_fundamentals', 'news:fetch_news']}
        activities={{
          'tool:data:fetch_fundamentals': activity('Fetching fundamentals', 'running'),
          'tool:news:fetch_news': activity('Fetching news', 'running'),
        }}
        width={60}
      />,
    );
    expect(frame.split('\n')).toEqual(['⠋ Fetching fundamentals  1s', '  ⎿ Fetching news']);
  });

  it('RunFooter: glyph, gap, then segments', () => {
    expect(frameOf(<RunFooter status="completed" elapsedMs={400} toolCount={4} partial={false} width={60} />)).toBe(
      '✓ 0.4s · 4 tools',
    );
    expect(frameOf(<RunFooter status="completed" elapsedMs={400} toolCount={4} partial unavailable={['news']} width={60} />)).toBe(
      '◐ partial · news unavailable · 0.4s · 4 tools',
    );
    expect(frameOf(<RunFooter status="failed" elapsedMs={400} toolCount={0} partial={false} width={60} />)).toBe(
      '✕ failed · 0.4s',
    );
  });

  it('Header: "FIN-AI  title · mode · model"', () => {
    const frame = frameOf(
      <Header title="Fake research session" mode="guided" model="claude-haiku-5.5" width={100} />,
    );
    expect(frame).toBe('FIN-AI  Fake research session · guided · claude-haiku-5.5');
  });

  it('Clarification: "HDFCBANK  HDFC Bank · NSE"', () => {
    const frame = frameOf(
      <Clarification
        candidates={[{ symbol: 'HDFCBANK', name: 'HDFC Bank', exchange: 'NSE' }] as never}
        lines={[]}
        width={60}
      />,
    );
    expect(frame).toBe('HDFCBANK  HDFC Bank · NSE');
  });

  it('Notice: glyph, then one space, then text', () => {
    expect(frameOf(<Notice kind="warn" text="Provider retrying" width={60} />)).toBe('⚠ Provider retrying');
  });
});

describe('inline spans add no extra spaces', () => {
  it('bold inside a paragraph keeps one space either side', () => {
    const frame = frameOf(renderMarkdown('RSI(14) is **77.9**, which is overbought.', 80) as ReactElement);
    expect(frame).toBe('RSI(14) is 77.9, which is overbought.');
    expect(frame).not.toContain('  ');
  });

  it('code span inside prose keeps one space either side', () => {
    const frame = frameOf(renderMarkdown('use `x` here', 80) as ReactElement);
    expect(frame).toBe('use x here');
  });
});

describe('markdown tables', () => {
  function expectAligned(frame: string): void {
    const lines = tableLines(frame);
    expect(lines.length).toBeGreaterThan(3);
    const width = displayWidth(lines[0] ?? '');
    const bars = barColumns(lines[0] ?? '');
    for (const line of lines) {
      expect(displayWidth(line)).toBe(width);
      expect(barColumns(line)).toEqual(bars);
    }
  }

  it('every line has equal width and bars in the same columns (80 cols)', () => {
    const md = '| Metric | Value |\n| --- | --- |\n| P/E ratio | 15.13 |\n| Price to book | 2.10 |\n| Return on equity | 13.75% |';
    const frame = frameOf(renderMarkdown(md, 80) as ReactElement);
    expect(frame).toContain('┌');
    expect(frame).toContain('└');
    expectAligned(frame);
    const lines = tableLines(frame);
    expect(lines[0]).toMatch(/^┌─+┬─+┐$/);
    expect(lines[2]).toMatch(/^├─+┼─+┤$/);
    expect(lines[lines.length - 1]).toMatch(/^└─+┴─+┘$/);
  });

  it('wrapping cell at 80 cols keeps every row aligned', () => {
    const long = 'Momentum is strong but stretched, so the RSI reading argues for waiting on a pullback before adding exposure again';
    const md = `| Metric | Commentary |\n| --- | --- |\n| RSI(14) | ${long} |\n| P/E | 15.13 |`;
    const frame = frameOf(renderMarkdown(md, 80) as ReactElement);
    // Top, header, rule, two lines for the wrapped RSI row, the P/E row, bottom: 7 lines.
    expect(tableLines(frame)).toHaveLength(7);
    expectAligned(frame);
    for (const line of frame.split('\n')) expect(displayWidth(line)).toBeLessThanOrEqual(80);
  });
});
