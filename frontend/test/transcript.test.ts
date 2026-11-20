import { describe, expect, it } from 'vitest';
import {
  type StableSplit,
  type TranscriptItem,
  commitFinal,
  commitStreamingText,
  runFooterItem,
  splitStableMarkdown,
  startDraft,
} from '../src/state/transcript.js';

/** Feed `text` in pieces of `size` characters and return the stable split after each piece. */
function feed(text: string, size: number): { prefixes: string[]; splits: StableSplit[] } {
  const prefixes: string[] = [];
  const splits: StableSplit[] = [];
  for (let end = size; end < text.length + size; end += size) {
    const prefix = text.slice(0, end);
    prefixes.push(prefix);
    splits.push(splitStableMarkdown(prefix));
  }
  return { prefixes, splits };
}

function assertInvariants(text: string, size: number): void {
  const { prefixes, splits } = feed(text, size);
  let previousStable: string[] = [];
  splits.forEach((split, step) => {
    const prefix = prefixes[step] ?? '';
    // stable + tail is always the text so far
    expect(split.stable.join('') + split.tail).toBe(prefix);
    // stable blocks never change once emitted
    expect(split.stable.slice(0, previousStable.length)).toEqual(previousStable);
    previousStable = split.stable;
  });
}

const FENCE = '```python\nprint("a")\n\nprint("b")\n\n```\n';
const TABLE = '| Metric | Value |\n| --- | ---: |\n| P/E | 15.1 |\n| P/B | 2.1 |\n';
const LIST = '- first point\n- second point\n\n- third point after a blank\n\n  continued indented\n';

describe('splitStableMarkdown', () => {
  it('returns the whole text as tail when there is no blank line', () => {
    expect(splitStableMarkdown('one line\nno blank')).toEqual({ stable: [], tail: 'one line\nno blank' });
  });

  it('closes a paragraph only after a blank line and a following block starts', () => {
    expect(splitStableMarkdown('Para one.\n\n')).toEqual({ stable: [], tail: 'Para one.\n\n' });
    expect(splitStableMarkdown('Para one.\n\nPara two')).toEqual({
      stable: ['Para one.\n\n'],
      tail: 'Para two',
    });
  });

  it('never splits inside an open fence, even across blank lines', () => {
    const open = '```python\nx = 1\n\ny = 2\n\n';
    expect(splitStableMarkdown(open)).toEqual({ stable: [], tail: open });
    const closedThenText = `${FENCE}Next paragraph\n`;
    expect(splitStableMarkdown(closedThenText)).toEqual({ stable: [FENCE], tail: 'Next paragraph\n' });
  });

  it('holds back a table until a plain line follows it', () => {
    expect(splitStableMarkdown(`${TABLE}\n`)).toEqual({ stable: [], tail: `${TABLE}\n` });
    expect(splitStableMarkdown(`${TABLE}\nNext\n`)).toEqual({ stable: [`${TABLE}\n`], tail: 'Next\n' });
  });

  it('holds back a list that may continue after a blank line', () => {
    expect(splitStableMarkdown(`${LIST}`)).toEqual({ stable: [], tail: LIST });
    expect(splitStableMarkdown(`- a\n\n- b\n\nClosing words\n`)).toEqual({
      stable: ['- a\n\n- b\n\n'],
      tail: 'Closing words\n',
    });
  });

  it('holds back a list whose next line is not complete yet', () => {
    expect(splitStableMarkdown('- a\n\nPlai')).toEqual({ stable: [], tail: '- a\n\nPlai' });
  });

  it('keeps the stable prefix contiguous: a held block holds back later blocks', () => {
    const text = `${TABLE}\n\nParagraph after table\n\nAnother\n`;
    const split = splitStableMarkdown(text);
    expect(split.stable.join('') + split.tail).toBe(text);
    expect(split.stable).toEqual([`${TABLE}\n\n`, 'Paragraph after table\n\n']);
    expect(split.tail).toBe('Another\n');
  });

  it('handles CRLF line endings', () => {
    expect(splitStableMarkdown('A\r\n\r\nB\r\n')).toEqual({ stable: ['A\r\n\r\n'], tail: 'B\r\n' });
  });
});

describe('streaming split across many deltas', () => {
  const document = [
    '## Research report',
    '',
    'HDFC Bank closed at **846.0**.',
    '',
    FENCE,
    'A second paragraph with `inline code`.',
    '',
    TABLE,
    'Closing paragraph.',
    '',
    LIST,
    'Final words.',
    '',
  ].join('\n');

  for (const size of [1, 2, 3, 5, 7, 16, 64]) {
    it(`keeps stable + tail equal to the text and stable blocks fixed (delta size ${size})`, () => {
      assertInvariants(document, size);
    });
  }

  it('never commits a fence, table or list in pieces', () => {
    const { splits } = feed(document, 3);
    for (const split of splits) {
      for (const block of split.stable) {
        const fences = block.match(/^ {0,3}```/gm)?.length ?? 0;
        expect(fences % 2).toBe(0);
        if (block.includes('| Metric')) expect(block).toContain('| P/B | 2.1 |');
        if (block.includes('- first point')) expect(block).toContain('- third point after a blank');
      }
    }
  });
});

describe('commit helpers', () => {
  const runId = 'run-1';
  const trail = (): TranscriptItem => ({
    kind: 'activity-trail',
    id: `${runId}:trail`,
    runId,
    collapsed: true,
    toolCount: 2,
    failedNouns: [],
    rows: [],
  });

  it('emits each stable block exactly once, in order, with the trail first', () => {
    const text = `Para one.\n\nPara two.\n\n${FENCE}Tail`;
    let draft = startDraft(runId);
    const emitted: TranscriptItem[] = [];
    for (let end = 4; end < text.length + 4; end += 4) {
      const result = commitStreamingText(draft, text.slice(0, end), trail);
      draft = result.draft;
      emitted.push(...result.items);
    }
    const chunks = emitted.filter((item) => item.kind === 'answer-chunk');
    expect(chunks.map((item) => (item.kind === 'answer-chunk' ? item.text : ''))).toEqual([
      'Para one.\n\n',
      'Para two.\n\n',
      FENCE,
    ]);
    expect(chunks.map((item) => (item.kind === 'answer-chunk' ? item.index : -1))).toEqual([0, 1, 2]);
    expect(emitted[0]?.kind).toBe('activity-trail');
    expect(emitted.filter((item) => item.kind === 'activity-trail')).toHaveLength(1);
  });

  it('commits the trail only when the first answer chunk commits', () => {
    const draft = startDraft(runId);
    const first = commitStreamingText(draft, 'Only a tail', trail);
    expect(first.items).toEqual([]);
    const second = commitStreamingText(first.draft, 'Only a tail\n\nNext', trail);
    expect(second.items.map((item) => item.kind)).toEqual(['activity-trail', 'answer-chunk']);
  });

  it('commits the live tail, sources, closing items and footer in order at finish', () => {
    const text = 'Stable.\n\nLive tail';
    const draft = startDraft(runId);
    const streamed = commitStreamingText(draft, 'Stable.\n\nLive', trail);
    const finish = commitFinal(streamed.draft, text, {
      trail,
      closing: [{ kind: 'notice', id: `${runId}:notice`, runId, tone: 'dim', text: 'note' }],
      sources: { kind: 'sources', id: `${runId}:sources`, runId, sources: [] },
      footer: runFooterItem(runId, { status: 'completed', elapsedMs: 1200, toolCount: 2, partial: false, sourceCount: 0, unavailable: [], reason: null }),
    });
    expect(finish.items.map((item) => item.kind)).toEqual([
      'answer-chunk',
      'sources',
      'notice',
      'run-footer',
    ]);
    const chunkTexts = finish.items.flatMap((item) => (item.kind === 'answer-chunk' ? [item.text] : []));
    expect(chunkTexts).toEqual(['Live tail']);
  });

  it('commits the trail first at finish when nothing streamed', () => {
    const finish = commitFinal(startDraft(runId), 'Short answer', {
      trail,
      closing: [],
      sources: null,
      footer: runFooterItem(runId, { status: 'completed', elapsedMs: null, toolCount: 2, partial: true, sourceCount: 0, unavailable: ['news'], reason: null }),
    });
    expect(finish.items.map((item) => item.kind)).toEqual(['activity-trail', 'answer-chunk', 'run-footer']);
  });
});
