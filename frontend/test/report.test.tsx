/**
 * Report components: layout at 80 and 120 columns, fail-closed parsing, and
 * the report rules (no wrapped table rows, no raw tool ids, nothing wider than the screen).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import type { ReportView as ReportData } from '../src/protocol/generated.js';
import { displayWidth } from '../src/render/format.js';
import { parseReport } from '../src/ui/report/parse.js';
import { ReportView } from '../src/ui/report/ReportView.js';
import { strengthBar } from '../src/ui/report/Signals.js';
import { sparklineText } from '../src/ui/report/Sparkline.js';
import { DIR, RAW_ID, frameOf, loadReport } from './support/report.js';

/** The table/signal row that starts with the label (not prose that merely mentions it). */
const lineWith = (frame: string, label: string): string =>
  frame.split('\n').find((l) => l.startsWith(`  ${label}`) || l.startsWith(`${label}`)) ?? '';

describe.each([80, 120])('ReportView at %i columns', (width) => {
  const full = frameOf(<ReportView report={loadReport('full')} width={width} />);

  it('keeps every line within the width and never wraps a table row', () => {
    for (const line of full.split('\n')) expect(displayWidth(line)).toBeLessThanOrEqual(width);
    for (const label of ['P/E', 'Price / book', 'Return on equity']) {
      expect(full.split('\n').filter((l) => l.includes(label) && /\d/.test(l)).length).toBeGreaterThan(0);
    }
  });

  it('shows the blocks in reading order', () => {
    const order = [
      '╭─ HDFCBANK',
      'Summary',
      'Key figures',
      'Technical signals',
      'Key drivers',
      'Risks and contrarian view',
      '┃ Final view',
      'Detailed analysis',
      'Evidence and limitations',
      'Sources',
      'Research aid based on provider data',
    ];
    const at = order.map((needle) => full.indexOf(needle));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });

  it('prints no raw tool ids and no leading-space wrapped prose', () => {
    expect(full).not.toMatch(RAW_ID);
  });

  it('card: price and change on the first row, borders aligned', () => {
    const card = full.split('\n').slice(0, 5);
    expect(card[0]).toMatch(/^╭─ HDFCBANK/);
    expect(card[0]?.endsWith('╮')).toBe(true);
    for (const line of card.slice(1, -1)) {
      if (line.startsWith('│')) expect(line.endsWith('│')).toBe(true);
    }
    expect(full).toContain('846.00');
    expect(full).toContain('+14.82% (1y)');
  });

  it('table: values right-aligned and sources are chips', () => {
    const pe = lineWith(full, 'P/E ');
    const pb = lineWith(full, 'Price / book');
    expect(pe).toMatch(/\[2\]$/);
    // Same right edge for the value column: both values end at the same column.
    const end = (line: string, value: string): number => displayWidth(line.slice(0, line.indexOf(value) + value.length));
    expect(end(pe, '15.13')).toBe(end(pb, '2.10'));
  });

  it('as-of column only when wide; sparkline inline only when wide', () => {
    const wide = width >= 100;
    expect(full.includes('as of')).toBe(true); // table header or card quote
    const quoteRow = full.split('\n')[1] ?? '';
    expect(/[▁-█]/.test(quoteRow)).toBe(wide);
    expect(full.includes('▁') || full.includes('█')).toBe(true);
  });
});

describe('ReportView variants', () => {
  it('partial: names the unavailable source and the reason once', () => {
    const frame = frameOf(<ReportView report={loadReport('partial')} width={100} />);
    expect(frame).toMatch(/Evidence ●●●○ 3\/4 sources · limited/);
    expect(frame).toContain('✕ news');
    expect(frame).toContain('news provider timed out');
    expect(frame.match(/news provider timed out/g)).toHaveLength(1);
  });

  it('lookup: compact card with no signals or drivers', () => {
    const frame = frameOf(<ReportView report={loadReport('lookup')} width={80} />);
    expect(frame).not.toContain('Technical signals');
    expect(frame).not.toContain('Key drivers');
    expect(frame).toContain('Sources');
    for (const line of frame.split('\n')) expect(displayWidth(line)).toBeLessThanOrEqual(80);
  });

  it('omits blocks with no data', () => {
    const base = loadReport('full');
    const bare: ReportData = {
      ...base,
      key_figures: [],
      signals: [],
      drivers: [],
      risks: [],
      final_view: null,
      detailed_analysis: null,
      sources: [],
      sparkline: null,
      quote: null,
    };
    const frame = frameOf(<ReportView report={bare} width={80} />);
    for (const title of ['Key figures', 'Technical signals', 'Key drivers', 'Risks', 'Final view', 'Detailed', 'Sources']) {
      expect(frame).not.toContain(title);
    }
    expect(frame).not.toMatch(/N\/A|—/);
    expect(frame).toContain('Summary');
  });

  it('signals: direction glyph, strength bar, unavailable shows ○', () => {
    const report: ReportData = {
      ...loadReport('full'),
      signals: [
        { name: 'RSI (14)', value_text: '77.95', direction: 'bearish', state_text: 'overbought', strength: 0.8, percentile_text: '93rd pct' },
        { name: 'Bollinger', value_text: '—', direction: 'unavailable', state_text: null, strength: null, percentile_text: null },
      ],
    };
    const frame = frameOf(<ReportView report={report} width={120} />);
    expect(lineWith(frame, 'RSI (14)')).toMatch(/▼ overbought\s+▰▰▰▰▱\s+93rd pct/);
    expect(lineWith(frame, 'Bollinger')).toMatch(/○ unavailable/);
  });
});

describe('helpers', () => {
  it('sparkline maps 0..1 to blocks and caps the points', () => {
    expect(sparklineText([0, 0.5, 1])).toBe('▁▅█');
    expect(sparklineText(Array.from({ length: 48 }, (_, i) => i / 47), 24)).toHaveLength(24);
  });

  it('strength bar', () => {
    expect(strengthBar(1)).toBe('▰▰▰▰▰');
    expect(strengthBar(0.2)).toBe('▰▱▱▱▱');
    expect(strengthBar(null)).toBe('     ');
  });
});

describe('parseReport fails closed', () => {
  const good = JSON.parse(
    readFileSync(path.join(DIR, 'report-full.json'), 'utf8'),
  ).finished.report as Record<string, unknown>;

  it('accepts the fixture', () => {
    expect(parseReport(good)).not.toBeNull();
  });

  it.each([
    ['null', null],
    ['not an object', 'text'],
    ['missing summary', { ...good, summary: undefined }],
    ['bad kind', { ...good, kind: 'essay' }],
    ['bad signal direction', { ...good, signals: [{ name: 'x', value_text: '1', direction: 'sideways' }] }],
    ['non-integer ref', { ...good, risks: [{ text: 'r', source_refs: ['a'] }] }],
    ['missing evidence', { ...good, evidence: undefined }],
  ])('rejects %s', (_name, value) => {
    expect(parseReport(value)).toBeNull();
  });

  it('drops only an invalid sparkline', () => {
    const parsed = parseReport({ ...good, sparkline: { points: [2, 3], period_text: '1y', low_text: '1', high_text: '2' } });
    expect(parsed).not.toBeNull();
    expect(parsed?.sparkline).toBeNull();
  });

  it('sanitises control sequences', () => {
    const parsed = parseReport({ ...good, summary: 'ok\x1b[31m red\x07' });
    expect(parsed?.summary).not.toMatch(/\x1b|\x07/);
  });
});

describe('source lines at 80 columns', () => {
  it('wrap with a hanging indent instead of being cut with an ellipsis', () => {
    const base = loadReport('full');
    const report: ReportData = {
      ...base,
      sources: [
        {
          ref: 1,
          label: 'Yahoo Finance fundamentals snapshot for the instrument',
          url: 'https://finance.yahoo.com/quote/HDFCBANK.NS/key-statistics/',
          host: 'finance.yahoo.com',
          retrieved_text: 'observed 2026-11-20 with a deliberately long freshness note',
          freshness_text: 'refreshed daily after the market close',
        },
      ],
    };
    const lines = frameOf(<ReportView report={report} width={80} />).split('\n');
    const start = lines.findIndex((l) => /^ {2}1 {2}Yahoo Finance/.test(l));
    expect(start).toBeGreaterThanOrEqual(0);
    const text = lines.slice(start, start + 4).join('\n');
    expect(text).toContain('after the market close');
    expect(text).not.toContain('…');
    expect(lines[start + 1]).toMatch(/^ {5}\S/); // hangs under the label (indent 2 + "1" + 2 gap)
    for (const line of lines) expect(displayWidth(line)).toBeLessThanOrEqual(80);
  });
});
