import { describe, expect, it } from 'vitest';
import { render } from 'ink-testing-library';
import type { ReactElement } from 'react';
import { ActivityTrail } from '../src/ui/ActivityTrail.js';
import { Answer } from '../src/ui/Answer.js';
import { Clarification } from '../src/ui/Clarification.js';
import { CommandOutput } from '../src/ui/CommandOutput.js';
import { Header } from '../src/ui/Header.js';
import { LiveActivity } from '../src/ui/LiveActivity.js';
import { Notice } from '../src/ui/Notice.js';
import { RunFooter } from '../src/ui/RunFooter.js';
import { Sources } from '../src/ui/Sources.js';
import { StreamingAnswer } from '../src/ui/StreamingAnswer.js';
import { TranscriptItemView } from '../src/ui/TranscriptItemView.js';
import { UserMessage } from '../src/ui/UserMessage.js';
import type { TranscriptItem } from '../src/state/transcript.js';
import type { ActivityState } from '../src/state/types.js';
import { displayWidth } from '../src/render/format.js';

const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;
const RAW_ID = /\b[a-z_]+:[a-z_]+\b/;
const WIDTHS = [80, 120] as const;

function frameOf(element: ReactElement): string {
  const { lastFrame, unmount } = render(element);
  const frame = (lastFrame() ?? '').replace(ANSI, '');
  unmount();
  return frame;
}

function expectFitsWidth(frame: string, width: number): void {
  for (const line of frame.split('\n')) {
    expect(displayWidth(line)).toBeLessThanOrEqual(width);
  }
}

const tool = (label: string, status: ActivityState['status'], detail: string | null = null): ActivityState => ({
  label,
  status,
  detail,
});

describe('transcript components at 80 and 120 columns', () => {
  for (const width of WIDTHS) {
    describe(`width ${width}`, () => {
      it('Header shows the brand, title, mode and model', () => {
        const frame = frameOf(<Header title="cf51ae03" mode="guided" model="claude-haiku-5.5" width={width} />);
        expect(frame).toContain('FIN-AI');
        expect(frame).toContain('cf51ae03 · guided · claude-haiku-5.5');
        expectFitsWidth(frame, width);
      });

      it('UserMessage renders the query after the prompt chevron', () => {
        const frame = frameOf(<UserMessage text="Can you analyse HDFC Bank?" width={width} />);
        expect(frame).toContain('› Can you analyse HDFC Bank?');
        expectFitsWidth(frame, width);
      });

      it('ActivityTrail shows the collapsed summary and failed nouns', () => {
        const frame = frameOf(
          <ActivityTrail
            toolCount={3}
            failedNouns={['news']}
            activities={{ 'tool:a': tool('Price history', 'completed') }}
            width={width}
          />,
        );
        expect(frame).toContain('Gathered evidence · 3 tools · news unavailable');
        expectFitsWidth(frame, width);
      });

      it('ActivityTrail lists each tool when expanded', () => {
        const frame = frameOf(
          <ActivityTrail
            expanded
            activities={{
              'tool:a': tool('Price history', 'completed'),
              'tool:b': tool('Fundamentals', 'failed', 'timeout'),
              model: tool('Contacting model', 'running'),
            }}
            width={width}
          />,
        );
        expect(frame).toContain('Gathered evidence · 2 tools');
        expect(frame).toContain('⎿ Price history · done');
        expect(frame).toContain('✕ Fundamentals · failed · timeout');
        expect(frame).not.toContain('Contacting model');
        expectFitsWidth(frame, width);
      });

      it('LiveActivity shows spinner, operation, elapsed time and at most three tools', () => {
        const activities: Record<string, ActivityState> = {
          'tool:1': tool('Price history', 'running'),
          'tool:2': tool('Fundamentals', 'running'),
          'tool:3': tool('News', 'running'),
          'tool:4': tool('Filings', 'running'),
        };
        const frame = frameOf(
          <LiveActivity
            frame={0}
            operation="Researching HDFC Bank"
            elapsedSeconds={12}
            activeTools={['1', '2', '3', '4']}
            activities={activities}
            width={width}
          />,
        );
        expect(frame).toContain('⠋ Researching HDFC Bank');
        expect(frame).toContain('12s');
        expect(frame).toContain('Price history');
        expect(frame).toContain('Fundamentals');
        expect(frame).toContain('News');
        expect(frame).not.toContain('Filings');
        expectFitsWidth(frame, width);
      });

      it('Answer puts the bullet on the first line of the Markdown', () => {
        const frame = frameOf(<Answer text={'## Executive summary\n\nHDFC is steady.'} width={width} />);
        const lines = frame.split('\n');
        expect(lines[0]).toContain('● Executive summary');
        expect(frame).toContain('HDFC is steady.');
        expectFitsWidth(frame, width);
      });

      it('StreamingAnswer draws the live tail without a bullet when asked', () => {
        const frame = frameOf(<StreamingAnswer text="still **streaming**" width={width} showBullet={false} />);
        expect(frame).toContain('still streaming');
        expect(frame).not.toContain('●');
        expectFitsWidth(frame, width);
      });

      it('Sources numbers each source and shows the host only when it differs from the label', () => {
        const frame = frameOf(
          <Sources
            sources={[
              { label: 'Yahoo Finance', url: 'https://finance.yahoo.com/q', host: 'finance.yahoo.com' },
              { label: 'finance.yahoo.com', url: 'https://finance.yahoo.com/x', host: 'finance.yahoo.com' },
              { label: 'Upstox', url: 'https://upstox.com/', host: null },
            ]}
            width={width}
          />,
        );
        expect(frame).toContain('1. Yahoo Finance · finance.yahoo.com');
        expect(frame).toContain('2. finance.yahoo.com');
        expect(frame).not.toContain('2. finance.yahoo.com ·');
        expect(frame).toContain('3. Upstox');
        expect(frame).not.toContain('3. Upstox ·');
        expectFitsWidth(frame, width);
      });

      it('Clarification aligns symbols and keeps passthrough lines', () => {
        const frame = frameOf(
          <Clarification
            candidates={[
              { symbol: 'HDFCBANK', name: 'HDFC Bank', exchange: 'NSE' },
              { symbol: 'HDFC', name: 'Housing Development Finance', exchange: 'BSE' },
            ]}
            lines={['Pick one to continue.']}
            width={width}
          />,
        );
        expect(frame).toContain('HDFCBANK  HDFC Bank · NSE');
        expect(frame).toContain('HDFC      Housing Development Finance · BSE');
        expect(frame).toContain('Pick one to continue.');
        expectFitsWidth(frame, width);
      });

      it('Notice uses the warn, fail and info glyphs', () => {
        const warn = frameOf(<Notice kind="warn" text="Review unavailable" width={width} />);
        const fail = frameOf(<Notice kind="fail" text="Provider failed" width={width} />);
        const info = frameOf(<Notice kind="info" text="Cancelled" width={width} />);
        expect(warn).toContain('⚠ Review unavailable');
        expect(fail).toContain('✕ Provider failed');
        expect(info).toContain('· Cancelled');
      });

      it('RunFooter reads duration, tools and partial status', () => {
        const ok = frameOf(
          <RunFooter
            status="completed"
            elapsedMs={12_400}
            toolCount={4}
            sourceCount={3}
            partial
            unavailable={['news']}
            width={width}
          />,
        );
        expect(ok).toContain('◐ partial · news unavailable · 12.4s · 4 tools · 3 sources');
        const failed = frameOf(
          <RunFooter
            status="failed"
            elapsedMs={3_000}
            toolCount={1}
            partial
            reason="The model provider did not respond"
            width={width}
          />,
        );
        expect(failed).toContain('✕ failed · The model provider did not respond · 3.0s · 1 tool');
        expect(failed).not.toContain('partial');
        const cancelled = frameOf(
          <RunFooter status="cancelled" elapsedMs={3_100} toolCount={2} partial width={width} />,
        );
        expect(cancelled).toContain('· cancelled · 3.1s · 2 tools');
        expect(cancelled).not.toContain('partial');
        expect(cancelled).toContain('· cancelled');
        expectFitsWidth(ok, width);
      });

      it('CommandOutput prints each line', () => {
        const frame = frameOf(<CommandOutput lines={['/help', '', '/clear  reset the screen']} width={width} />);
        expect(frame).toContain('/help');
        expect(frame).toContain('/clear  reset the screen');
        expectFitsWidth(frame, width);
      });

      it('TranscriptItemView dispatches every kind', () => {
        const items: TranscriptItem[] = [
          { kind: 'header', id: 'h', title: 'S', mode: 'guided', model: 'm' },
          { kind: 'user', id: 'u', runId: 'r', text: 'hi there' },
          { kind: 'activity-trail', id: 't', runId: 'r', collapsed: true, toolCount: 2, failedNouns: [], rows: [] },
          { kind: 'answer-chunk', id: 'c', runId: 'r', index: 0, text: 'Answer body' },
          { kind: 'sources', id: 's', runId: 'r', sources: [{ label: 'Src', url: 'https://a.test/' }] },
          {
            kind: 'clarification',
            id: 'k',
            runId: 'r',
            candidates: [{ symbol: 'TCS', name: 'Tata Consultancy', exchange: 'NSE' }],
            lines: [],
          },
          { kind: 'notice', id: 'n', runId: 'r', tone: 'loss', text: 'boom' },
          { kind: 'run-footer', id: 'f', runId: 'r', status: 'completed', elapsedMs: 900, toolCount: 2, sourceCount: 0, partial: false, unavailable: [], reason: null },
          { kind: 'command-output', id: 'o', lines: ['out'] },
        ];
        const frames = items.map((item) => frameOf(<TranscriptItemView item={item} width={width} />));
        expect(frames[0]).toContain('FIN-AI');
        expect(frames[1]).toContain('› hi there');
        expect(frames[2]).toContain('Gathered evidence · 2 tools');
        expect(frames[3]).toContain('● Answer body');
        expect(frames[4]).toContain('Src');
        expect(frames[5]).toContain('TCS  Tata Consultancy · NSE');
        expect(frames[6]).toContain('✕ boom');
        expect(frames[7]).toContain('✓ 0.9s · 2 tools');
        expect(frames[8]).toContain('out');
        for (const frame of frames) expectFitsWidth(frame, width);
      });
    });
  }

  it('ActivityTrail never prints a raw tool id, even when fed one', () => {
    const frame = frameOf(
      <ActivityTrail
        expanded
        toolCount={2}
        failedNouns={['news:fe12ab']}
        activities={{
          'tool:news:fe12ab': tool('news:fe12ab', 'failed', 'news:fe12ab timed out'),
          'tool:quotes': tool('Price history', 'completed', 'fundamentals:get_ratios'),
        }}
        width={80}
      />,
    );
    expect(frame).toContain('Price history');
    expect(frame).not.toMatch(RAW_ID);
    expect(frame).not.toContain('news:fe12ab');
    expect(frame).not.toContain('fundamentals:get_ratios');
  });

  it('ActivityTrail renders nothing for a chat-only run', () => {
    const frame = frameOf(
      <ActivityTrail
        toolCount={0}
        expanded
        activities={{ model: tool('Contacting model', 'completed') }}
        width={80}
      />,
    );
    expect(frame).toBe('');
  });

  it('LiveActivity never prints raw ids and falls back to a neutral operation', () => {
    const frame = frameOf(
      <LiveActivity
        frame={3}
        operation="news:fe12ab"
        elapsedSeconds={1}
        activeTools={['x']}
        activities={{ 'tool:x': tool('quotes:raw', 'running') }}
        width={80}
      />,
    );
    expect(frame).toContain('Working');
    expect(frame).not.toMatch(RAW_ID);
  });
});
