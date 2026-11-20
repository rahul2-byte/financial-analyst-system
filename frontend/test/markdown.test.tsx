import { describe, expect, it } from 'vitest';
import { render as inkRender } from 'ink-testing-library';
import { render as renderMarkdown, fitColumns } from '../src/render/markdown.js';
import { displayWidth, truncate, wrapWords, hardWrap, formatSeconds, pluralize, hostOf } from '../src/render/format.js';

const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;

function md(text: string, width = 80): string {
  const { lastFrame, unmount } = inkRender(<>{renderMarkdown(text, width)}</>);
  const frame = (lastFrame() ?? '').replace(ANSI, '');
  unmount();
  return frame;
}

describe('markdown renderer', () => {
  it('renders empty input as nothing', () => {
    expect(md('   \n')).toBe('');
  });

  it('drops raw citation ids it cannot map to the Sources list and keeps numbered refs', () => {
    const frame = md('Valuation looks fair. [citations: c2, c3]\n\n- Trend holds [citation: c1] and [2]. Margins hold [c4, c5].');
    expect(frame).not.toMatch(/\bc\d\b/);
    expect(frame).not.toContain('citation');
    expect(frame).toContain('Valuation looks fair.');
    expect(frame).not.toMatch(/fair\. +$/m);
    expect(frame).toContain('Trend holds and [2]. Margins hold.');
  });

  it('renders a heading as its text without the hash marks', () => {
    const frame = md('## Executive summary');
    expect(frame).toContain('Executive summary');
    expect(frame).not.toContain('##');
  });

  it('renders paragraphs with bold, italic and inline code', () => {
    const frame = md('Price is **up** and *steady* via `ratio_x`.');
    expect(frame).toContain('Price is up and steady via');
    expect(frame).toContain('ratio_x');
    expect(frame).not.toContain('**');
    expect(frame).not.toContain('`');
  });

  it('renders an unordered list with bullets', () => {
    const frame = md('- alpha\n- beta');
    expect(frame).toContain('• alpha');
    expect(frame).toContain('• beta');
  });

  it('indents nested lists under their parent', () => {
    const frame = md('1. one\n   - inner\n2. two');
    const lines = frame.split('\n');
    const one = lines.find((line) => line.includes('one'));
    const inner = lines.find((line) => line.includes('inner'));
    const two = lines.find((line) => line.includes('two'));
    expect(one).toBeDefined();
    expect(inner).toBeDefined();
    expect(two).toBeDefined();
    expect(one?.indexOf('1.')).toBe(0);
    expect(two?.indexOf('2.')).toBe(0);
    expect(inner?.indexOf('•')).toBeGreaterThan(one?.indexOf('1.') ?? -1);
  });

  it('fits a wide table into 80 columns with rule-drawn borders', () => {
    const long = 'Strong operating margins with steady free cash flow across the last eight quarters';
    const frame = md(
      `| Metric | Value | Commentary |\n| --- | --- | --- |\n| Margin | 24% | ${long} |\n| Growth | 12% | ${long} |`,
      80,
    );
    for (const line of frame.split('\n')) {
      expect(displayWidth(line)).toBeLessThanOrEqual(80);
    }
    expect(frame).toContain('┌');
    expect(frame).toContain('┘');
    expect(frame).toContain('Metric');
    expect(frame).toContain('Strong operating');
  });

  it('renders a fenced code block verbatim', () => {
    const frame = md('```ts\nconst x = 1\n```');
    expect(frame).toContain('const x = 1');
    expect(frame).not.toContain('```');
  });

  it('renders a link as text (host)', () => {
    const frame = md('See [Yahoo quotes](https://www.finance.yahoo.com/quote/HDFCBANK.NS) for detail.');
    expect(frame).toContain('Yahoo quotes (finance.yahoo.com)');
  });

  it('renders blockquotes behind a bar', () => {
    const frame = md('> Data may be delayed.');
    expect(frame).toContain('│');
    expect(frame).toContain('Data may be delayed.');
  });

  it('renders a horizontal rule across the width', () => {
    const frame = md('before\n\n---\n\nafter', 20);
    expect(frame).toContain('─'.repeat(20));
  });

  it('wraps long paragraphs inside the width', () => {
    const frame = md('word '.repeat(60), 40);
    for (const line of frame.split('\n')) {
      expect(displayWidth(line)).toBeLessThanOrEqual(40);
    }
  });
});

describe('format helpers', () => {
  it('fitColumns shrinks the widest column first', () => {
    expect(fitColumns([10, 4, 30], 20)).toEqual([8, 4, 8]);
    expect(fitColumns([3, 3], 10)).toEqual([3, 3]);
  });

  it('formats seconds and pluralises', () => {
    expect(formatSeconds(12_400)).toBe('12.4s');
    expect(formatSeconds(65_000)).toBe('1m 05.0s');
    expect(pluralize(1, 'tool')).toBe('1 tool');
    expect(pluralize(6, 'tool')).toBe('6 tools');
  });

  it('truncates by display width with an ellipsis', () => {
    expect(truncate('abcdef', 4)).toBe('abc…');
    expect(truncate('ab', 4)).toBe('ab');
    expect(displayWidth(truncate('日本語テキスト', 5))).toBeLessThanOrEqual(5);
  });

  it('wraps words and hard-breaks overlong words', () => {
    expect(wrapWords('one two three', 7)).toEqual(['one two', 'three']);
    expect(hardWrap('abcdefg', 3)).toEqual(['abc', 'def', 'g']);
  });

  it('extracts the host without www', () => {
    expect(hostOf('https://www.upstox.com/a')).toBe('upstox.com');
    expect(hostOf('not a url')).toBeNull();
  });
});
