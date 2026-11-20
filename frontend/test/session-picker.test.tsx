import { render } from 'ink-testing-library';
import { describe, expect, it, vi } from 'vitest';

import type { SessionSummary } from '../src/protocol/generated.js';
import { SessionPicker, filterSessions } from '../src/ui/SessionPicker.js';

const ANSI = /\x1b\[[0-9;]*m/g;
const strip = (frame: string | undefined): string => (frame ?? '').replace(ANSI, '');
const tick = (ms = 15): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));
const UP = '\x1b[A';
const DOWN = '\x1b[B';

const SESSIONS: SessionSummary[] = [
  {
    id: 'abcd1234-0000-0000-0000-000000000001',
    title: 'Infosys margins',
    message_count: 4,
    run_count: 2,
    last_status: 'completed',
    last_activity: '2026-11-20T10:00:00Z',
  },
  {
    id: 'ffff0000-0000-0000-0000-000000000002',
    title: 'HDFC bank outlook',
    message_count: 9,
    run_count: 3,
    last_status: 'completed',
    last_activity: '2026-11-19T09:00:00Z',
  },
];

describe('filterSessions', () => {
  it('keeps everything for an empty query', () => {
    expect(filterSessions(SESSIONS, '  ')).toHaveLength(2);
  });

  it('matches titles case-insensitively', () => {
    expect(filterSessions(SESSIONS, 'hdfc').map((session) => session.id)).toEqual([SESSIONS[1]!.id]);
  });

  it('matches an id prefix but not a middle substring', () => {
    expect(filterSessions(SESSIONS, 'ffff').map((session) => session.id)).toEqual([SESSIONS[1]!.id]);
    expect(filterSessions(SESSIONS, '0000-0000')).toEqual([]);
  });
});

describe('SessionPicker component', () => {
  it('renders the session titles and the id prefix', () => {
    const { lastFrame, unmount } = render(
      <SessionPicker sessions={SESSIONS} onSelect={() => {}} onClose={() => {}} />,
    );
    const frame = strip(lastFrame());
    expect(frame).toContain('Infosys margins');
    expect(frame).toContain('HDFC bank outlook');
    expect(frame).toContain('abcd1234');
    unmount();
  });

  it('typing filters the list', async () => {
    const { stdin, lastFrame, unmount } = render(
      <SessionPicker sessions={SESSIONS} onSelect={() => {}} onClose={() => {}} />,
    );
    stdin.write('hdfc');
    await tick();
    const frame = strip(lastFrame());
    expect(frame).toContain('HDFC bank outlook');
    expect(frame).not.toContain('Infosys margins');
    unmount();
  });

  it('shows a notice when nothing matches and does not select', async () => {
    const onSelect = vi.fn();
    const { stdin, lastFrame, unmount } = render(
      <SessionPicker sessions={SESSIONS} onSelect={onSelect} onClose={() => {}} />,
    );
    stdin.write('zzz');
    await tick();
    expect(strip(lastFrame())).toContain('No sessions match');
    stdin.write('\r');
    await tick();
    expect(onSelect).not.toHaveBeenCalled();
    unmount();
  });

  it('↓ then Enter selects the second session', async () => {
    const onSelect = vi.fn();
    const { stdin, unmount } = render(
      <SessionPicker sessions={SESSIONS} onSelect={onSelect} onClose={() => {}} />,
    );
    stdin.write(DOWN);
    await tick();
    stdin.write('\r');
    await tick();
    expect(onSelect).toHaveBeenCalledWith(SESSIONS[1]!.id);
    unmount();
  });

  it('↑ at the top keeps the first session selected', async () => {
    const onSelect = vi.fn();
    const { stdin, unmount } = render(
      <SessionPicker sessions={SESSIONS} onSelect={onSelect} onClose={() => {}} />,
    );
    stdin.write(UP);
    await tick();
    stdin.write('\r');
    await tick();
    expect(onSelect).toHaveBeenCalledWith(SESSIONS[0]!.id);
    unmount();
  });

  it('Esc closes the picker without selecting', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const { stdin, unmount } = render(
      <SessionPicker sessions={SESSIONS} onSelect={onSelect} onClose={onClose} />,
    );
    stdin.write('\x1b');
    await tick();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
    unmount();
  });
});
