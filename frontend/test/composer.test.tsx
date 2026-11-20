import { render } from 'ink-testing-library';
import { describe, expect, it, vi } from 'vitest';

import {
  Composer,
  PLACEHOLDER,
  composerReducer,
  initialComposerState,
  type ComposerState,
} from '../src/ui/Composer.js';
import { EXIT_WINDOW_MS } from '../src/ui/hooks/useKeybindings.js';

const ANSI = /\x1b\[[0-9;]*m/g;
const strip = (frame: string | undefined): string => (frame ?? '').replace(ANSI, '');
const tick = (ms = 15): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

function typed(text: string, from: ComposerState = initialComposerState()): ComposerState {
  return composerReducer(from, { type: 'insert', text });
}

describe('composerReducer: editing', () => {
  it('inserts at the cursor and advances it', () => {
    const state = typed('helo');
    const moved = composerReducer(state, { type: 'left' });
    const fixed = composerReducer(moved, { type: 'insert', text: 'l' });
    expect(fixed.value).toBe('hello');
    expect(fixed.cursor).toBe(4);
  });

  it('backspace removes the character before the cursor and stops at 0', () => {
    const state = composerReducer(typed('ab'), { type: 'backspace' });
    expect(state.value).toBe('a');
    expect(composerReducer(initialComposerState(), { type: 'backspace' }).value).toBe('');
  });

  it('backspace removes a whole surrogate pair', () => {
    const state = composerReducer(typed('x😀'), { type: 'backspace' });
    expect(state.value).toBe('x');
  });

  it('newline inserts a line break without submitting', () => {
    const state = composerReducer(typed('a'), { type: 'newline' });
    expect(state.value).toBe('a\n');
    expect(state.cursor).toBe(2);
  });

  it('backslashNewline replaces a trailing backslash with a newline', () => {
    const state = composerReducer(typed('line\\'), { type: 'backslashNewline' });
    expect(state.value).toBe('line\n');
    expect(state.cursor).toBe(5);
  });

  it('backslashNewline without a backslash just inserts a newline', () => {
    expect(composerReducer(typed('ab'), { type: 'backslashNewline' }).value).toBe('ab\n');
  });

  it('a multi-line paste lands as one insert and keeps the newlines', () => {
    const state = composerReducer(initialComposerState(['old']), { type: 'insert', text: 'one\ntwo\nthree' });
    expect(state.value).toBe('one\ntwo\nthree');
    expect(state.history).toEqual(['old']);
  });

  it('readline keys: line start/end, word moves, word delete, kill to line start', () => {
    const base = typed('alpha beta\ngamma delta');
    expect(composerReducer(base, { type: 'lineStart' }).cursor).toBe(11);
    expect(composerReducer({ ...base, cursor: 15 }, { type: 'lineEnd' }).cursor).toBe(22);
    expect(composerReducer(base, { type: 'wordLeft' }).cursor).toBe(17);
    expect(composerReducer({ ...base, cursor: 0 }, { type: 'wordRight' }).cursor).toBe(5);
    expect(composerReducer(base, { type: 'deleteWordBack' }).value).toBe('alpha beta\ngamma ');
    const killed = composerReducer({ ...base, cursor: 14 }, { type: 'killToLineStart' });
    expect(killed.value).toBe('alpha beta\nma delta');
    expect(killed.cursor).toBe(11);
  });
});

describe('composerReducer: ↑/↓ between lines and history', () => {
  it('↑ moves the cursor up a line when not on the first line', () => {
    const state = composerReducer(typed('first\nsecond'), { type: 'up' });
    expect(state.value).toBe('first\nsecond');
    expect(state.cursor).toBe(5);
    expect(state.historyIndex).toBeNull();
  });

  it('↑ on the first line browses history from the newest entry, then older ones', () => {
    const start = initialComposerState(['q1', 'q2']);
    const first = composerReducer(start, { type: 'up' });
    expect(first.value).toBe('q2');
    expect(first.historyIndex).toBe(1);
    const second = composerReducer(first, { type: 'up' });
    expect(second.value).toBe('q1');
    expect(second.historyIndex).toBe(0);
  });

  it('↓ on the last line walks forward and restores the unsent draft at the end', () => {
    const start = typed('draft', initialComposerState(['q1', 'q2']));
    const back = composerReducer(start, { type: 'up' });
    const back2 = composerReducer(back, { type: 'up' });
    const forward = composerReducer(back2, { type: 'down' });
    expect(forward.value).toBe('q2');
    const restored = composerReducer(forward, { type: 'down' });
    expect(restored.value).toBe('draft');
    expect(restored.historyIndex).toBeNull();
  });

  it('↓ on the last line with no browsing does nothing', () => {
    const state = typed('abc');
    expect(composerReducer(state, { type: 'down' })).toBe(state);
  });

  it('submitted records the text, clears the composer and skips empty or repeated entries', () => {
    const submitted = composerReducer(typed('hello'), { type: 'submitted' });
    expect(submitted.value).toBe('');
    expect(submitted.history).toEqual(['hello']);
    const repeated = composerReducer(typed('hello', submitted), { type: 'submitted' });
    expect(repeated.history).toEqual(['hello']);
    const blank = composerReducer(typed('   ', repeated), { type: 'submitted' });
    expect(blank.history).toEqual(['hello']);
  });
});

describe('composerReducer: completion', () => {
  it('completionMove wraps around the list', () => {
    const state = initialComposerState();
    expect(composerReducer(state, { type: 'completionMove', delta: -1, count: 3 }).completionIndex).toBe(2);
    const wrapped = composerReducer({ ...state, completionIndex: 2 }, { type: 'completionMove', delta: 1, count: 3 });
    expect(wrapped.completionIndex).toBe(0);
  });

  it('editing the text reopens a dismissed completion', () => {
    const dismissed = composerReducer(typed('/he'), { type: 'dismiss' });
    expect(dismissed.dismissed).toBe(true);
    expect(composerReducer(dismissed, { type: 'insert', text: 'l' }).dismissed).toBe(false);
  });
});

describe('Composer component', () => {
  it('shows the prompt, the placeholder and a rule-coloured top border', () => {
    const { lastFrame, unmount } = render(<Composer mode="idle" onSubmit={() => {}} />);
    const frame = strip(lastFrame());
    expect(frame).toContain('›');
    expect(frame).toContain(PLACEHOLDER);
    expect(frame.split('\n')[0]).toMatch(/─+/);
    unmount();
  });

  it('typing shows the text and Enter submits it', async () => {
    const onSubmit = vi.fn();
    const { stdin, lastFrame, unmount } = render(<Composer mode="idle" onSubmit={onSubmit} />);
    stdin.write('AAPL');
    await tick();
    expect(strip(lastFrame())).toContain('AAPL');
    stdin.write('\r');
    await tick();
    expect(onSubmit).toHaveBeenCalledWith('AAPL', 'submit');
    unmount();
  });

  it('Enter while running queues the prompt', async () => {
    const onSubmit = vi.fn();
    const { stdin, unmount } = render(<Composer mode="running" onSubmit={onSubmit} />);
    stdin.write('next');
    await tick();
    stdin.write('\r');
    await tick();
    expect(onSubmit).toHaveBeenCalledWith('next', 'queue');
    unmount();
  });

  it('Ctrl+J adds a second line and does not submit', async () => {
    const onSubmit = vi.fn();
    const { stdin, lastFrame, unmount } = render(<Composer mode="idle" onSubmit={onSubmit} />);
    stdin.write('one');
    await tick();
    stdin.write('\n');
    await tick();
    stdin.write('two');
    await tick();
    expect(onSubmit).not.toHaveBeenCalled();
    const frame = strip(lastFrame());
    expect(frame).toContain('one');
    expect(frame).toContain('two');
    unmount();
  });

  it('a bracketed paste with several lines is one input and does not submit', async () => {
    const onSubmit = vi.fn();
    const { stdin, lastFrame, unmount } = render(<Composer mode="idle" onSubmit={onSubmit} />);
    stdin.write('\x1b[200~first line\nsecond line\x1b[201~');
    await tick();
    expect(onSubmit).not.toHaveBeenCalled();
    const frame = strip(lastFrame());
    expect(frame).toContain('first line');
    expect(frame).toContain('second line');
    unmount();
  });

  it('↑ recalls the previous prompt from history', async () => {
    const { stdin, lastFrame, unmount } = render(
      <Composer mode="idle" history={['first query', 'second query']} onSubmit={() => {}} />,
    );
    stdin.write('\x1b[A');
    await tick();
    expect(strip(lastFrame())).toContain('second query');
    unmount();
  });

  it('Tab completes a partial command name to the selected command', async () => {
    const onSubmit = vi.fn();
    const { stdin, lastFrame, unmount } = render(<Composer mode="idle" onSubmit={onSubmit} />);
    stdin.write('/he');
    await tick();
    expect(strip(lastFrame())).toContain('/help');
    stdin.write('\t');
    await tick();
    // Ink trims the trailing cursor cell from the frame, so check the value via submit.
    stdin.write('\r');
    await tick();
    expect(onSubmit).toHaveBeenCalledWith('/help ', 'submit');
    unmount();
  });

  it('Esc closes the completion list while typing a command', async () => {
    const { stdin, lastFrame, unmount } = render(<Composer mode="idle" onSubmit={() => {}} />);
    stdin.write('/');
    await tick();
    expect(strip(lastFrame())).toContain('/clear');
    stdin.write('\x1b');
    await tick();
    expect(strip(lastFrame())).not.toContain('/clear');
    unmount();
  });

  it('Ctrl+C on an empty composer arms the exit, and a second press within the window exits', async () => {
    let now = 0;
    const onAction = vi.fn();
    const { stdin, unmount } = render(
      <Composer mode="idle" onSubmit={() => {}} onAction={onAction} now={() => now} />,
    );
    stdin.write('\x03');
    await tick();
    expect(onAction).toHaveBeenLastCalledWith({ type: 'armExit' });
    now = EXIT_WINDOW_MS - 1;
    stdin.write('\x03');
    await tick();
    expect(onAction).toHaveBeenLastCalledWith({ type: 'exit' });
    unmount();
  });

  it('Ctrl+C while running is passed up as cancelRun', async () => {
    const onAction = vi.fn();
    const { stdin, unmount } = render(<Composer mode="running" onSubmit={() => {}} onAction={onAction} />);
    stdin.write('\x03');
    await tick();
    expect(onAction).toHaveBeenLastCalledWith({ type: 'cancelRun' });
    unmount();
  });
});
