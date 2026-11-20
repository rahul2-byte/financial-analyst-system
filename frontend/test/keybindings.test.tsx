import type { Key } from 'ink';
import { describe, expect, it } from 'vitest';

import {
  EXIT_WINDOW_MS,
  cleanText,
  resolveKey,
  type KeyContext,
  type KeyMode,
} from '../src/ui/hooks/useKeybindings.js';

const BASE_KEY: Key = {
  upArrow: false,
  downArrow: false,
  leftArrow: false,
  rightArrow: false,
  pageDown: false,
  pageUp: false,
  home: false,
  end: false,
  return: false,
  escape: false,
  ctrl: false,
  shift: false,
  tab: false,
  backspace: false,
  delete: false,
  meta: false,
  super: false,
  hyper: false,
  capsLock: false,
  numLock: false,
} as Key;

function key(partial: Partial<Key> = {}): Key {
  return { ...BASE_KEY, ...partial } as Key;
}

function ctx(partial: Partial<KeyContext> = {}): KeyContext {
  return {
    composerEmpty: false,
    completionOpen: false,
    charBeforeCursor: '',
    now: 10_000,
    lastCtrlCAt: null,
    ...partial,
  };
}

const ENTER = key({ return: true });
const CTRL_C = key({ ctrl: true });
const ESC = key({ escape: true, meta: true });

describe('resolveKey: idle', () => {
  it('Enter submits', () => {
    expect(resolveKey('idle', '', ENTER, ctx())).toEqual({ type: 'submit' });
  });

  it('Shift+Enter inserts a newline', () => {
    expect(resolveKey('idle', '', key({ return: true, shift: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'newline' },
    });
  });

  it('Ctrl+J (raw LF) inserts a newline', () => {
    expect(resolveKey('idle', '\n', key(), ctx())).toEqual({ type: 'edit', op: { type: 'newline' } });
  });

  it('a backslash before the cursor plus Enter inserts a newline and drops the backslash', () => {
    expect(resolveKey('idle', '', ENTER, ctx({ charBeforeCursor: '\\' }))).toEqual({
      type: 'edit',
      op: { type: 'backslashNewline' },
    });
  });

  it('Esc closes an open completion', () => {
    expect(resolveKey('idle', '', ESC, ctx({ completionOpen: true }))).toEqual({ type: 'closeCompletion' });
  });

  it('Esc with no completion is a no-op', () => {
    expect(resolveKey('idle', '', ESC, ctx())).toEqual({ type: 'none' });
  });

  it('Ctrl+C clears a non-empty composer', () => {
    expect(resolveKey('idle', 'c', CTRL_C, ctx())).toEqual({ type: 'clearComposer' });
  });

  it('Ctrl+C on an empty composer arms the exit on the first press', () => {
    expect(resolveKey('idle', 'c', CTRL_C, ctx({ composerEmpty: true }))).toEqual({ type: 'armExit' });
  });

  it('a second Ctrl+C within 1.5 s on an empty composer exits', () => {
    const result = resolveKey(
      'idle',
      'c',
      CTRL_C,
      ctx({ composerEmpty: true, now: 10_000 + EXIT_WINDOW_MS, lastCtrlCAt: 10_000 }),
    );
    expect(result).toEqual({ type: 'exit' });
  });

  it('a second Ctrl+C after 1.5 s only re-arms', () => {
    const result = resolveKey(
      'idle',
      'c',
      CTRL_C,
      ctx({ composerEmpty: true, now: 10_000 + EXIT_WINDOW_MS + 1, lastCtrlCAt: 10_000 }),
    );
    expect(result).toEqual({ type: 'armExit' });
  });

  it('Ctrl+D exits on an empty composer', () => {
    expect(resolveKey('idle', 'd', key({ ctrl: true }), ctx({ composerEmpty: true }))).toEqual({ type: 'exit' });
  });

  it('Ctrl+D does nothing with text in the composer', () => {
    expect(resolveKey('idle', 'd', key({ ctrl: true }), ctx())).toEqual({ type: 'none' });
  });

  it('↑ and ↓ move through history, or the completion selection when it is open', () => {
    expect(resolveKey('idle', '', key({ upArrow: true }), ctx())).toEqual({ type: 'edit', op: { type: 'up' } });
    expect(resolveKey('idle', '', key({ downArrow: true }), ctx())).toEqual({ type: 'edit', op: { type: 'down' } });
    expect(resolveKey('idle', '', key({ upArrow: true }), ctx({ completionOpen: true }))).toEqual({
      type: 'completionUp',
    });
    expect(resolveKey('idle', '', key({ downArrow: true }), ctx({ completionOpen: true }))).toEqual({
      type: 'completionDown',
    });
  });

  it('Tab accepts the completion', () => {
    expect(resolveKey('idle', '', key({ tab: true }), ctx())).toEqual({ type: 'complete' });
  });

  it('Ctrl+O toggles activity details and Ctrl+L clears the screen', () => {
    expect(resolveKey('idle', 'o', key({ ctrl: true }), ctx())).toEqual({ type: 'toggleDetails' });
    expect(resolveKey('idle', 'l', key({ ctrl: true }), ctx())).toEqual({ type: 'clearScreen' });
  });

  it('Ctrl+A/E/W/U and Alt+←/→ do readline editing', () => {
    expect(resolveKey('idle', 'a', key({ ctrl: true }), ctx())).toEqual({ type: 'edit', op: { type: 'lineStart' } });
    expect(resolveKey('idle', 'e', key({ ctrl: true }), ctx())).toEqual({ type: 'edit', op: { type: 'lineEnd' } });
    expect(resolveKey('idle', 'w', key({ ctrl: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'deleteWordBack' },
    });
    expect(resolveKey('idle', 'u', key({ ctrl: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'killToLineStart' },
    });
    expect(resolveKey('idle', '', key({ leftArrow: true, meta: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'wordLeft' },
    });
    expect(resolveKey('idle', '', key({ rightArrow: true, meta: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'wordRight' },
    });
  });

  it('bracketed paste is inserted as one multi-line edit and never submits', () => {
    expect(resolveKey('idle', '[200~first\nsecond\x1b[201~', key(), ctx())).toEqual({
      type: 'edit',
      op: { type: 'insert', text: 'first\nsecond' },
    });
  });
});

describe('resolveKey: running', () => {
  it('Enter queues the prompt', () => {
    expect(resolveKey('running', '', ENTER, ctx())).toEqual({ type: 'queue' });
  });

  it('Shift+Enter, Ctrl+J and \\+Enter insert a newline', () => {
    expect(resolveKey('running', '', key({ return: true, shift: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'newline' },
    });
    expect(resolveKey('running', '\n', key(), ctx())).toEqual({ type: 'edit', op: { type: 'newline' } });
    expect(resolveKey('running', '', ENTER, ctx({ charBeforeCursor: '\\' }))).toEqual({
      type: 'edit',
      op: { type: 'backslashNewline' },
    });
  });

  it('Esc cancels the run', () => {
    expect(resolveKey('running', '', ESC, ctx())).toEqual({ type: 'cancelRun' });
  });

  it('Ctrl+C cancels the run, not the composer', () => {
    expect(resolveKey('running', 'c', CTRL_C, ctx())).toEqual({ type: 'cancelRun' });
    expect(resolveKey('running', 'c', CTRL_C, ctx({ composerEmpty: true }))).toEqual({ type: 'cancelRun' });
  });

  it('Ctrl+D does nothing', () => {
    expect(resolveKey('running', 'd', key({ ctrl: true }), ctx({ composerEmpty: true }))).toEqual({ type: 'none' });
  });

  it('↑/↓, Tab, Ctrl+O and Ctrl+L behave as in idle', () => {
    expect(resolveKey('running', '', key({ upArrow: true }), ctx())).toEqual({ type: 'edit', op: { type: 'up' } });
    expect(resolveKey('running', '', key({ tab: true }), ctx())).toEqual({ type: 'complete' });
    expect(resolveKey('running', 'o', key({ ctrl: true }), ctx())).toEqual({ type: 'toggleDetails' });
    expect(resolveKey('running', 'l', key({ ctrl: true }), ctx())).toEqual({ type: 'clearScreen' });
  });

  it('readline editing works while running', () => {
    expect(resolveKey('running', 'u', key({ ctrl: true }), ctx())).toEqual({
      type: 'edit',
      op: { type: 'killToLineStart' },
    });
  });
});

describe('resolveKey: picker', () => {
  it('Enter resumes the selected session', () => {
    expect(resolveKey('picker', '', ENTER, ctx())).toEqual({ type: 'pickerSelect' });
  });

  it('Esc closes the picker', () => {
    expect(resolveKey('picker', '', ESC, ctx())).toEqual({ type: 'pickerClose' });
  });

  it('Ctrl+C closes the picker', () => {
    expect(resolveKey('picker', 'c', CTRL_C, ctx())).toEqual({ type: 'pickerClose' });
  });

  it('↑ and ↓ move the selection', () => {
    expect(resolveKey('picker', '', key({ upArrow: true }), ctx())).toEqual({ type: 'pickerUp' });
    expect(resolveKey('picker', '', key({ downArrow: true }), ctx())).toEqual({ type: 'pickerDown' });
  });

  it('printable text filters the list and Backspace removes from it', () => {
    expect(resolveKey('picker', 'b', key(), ctx())).toEqual({ type: 'pickerInsert', text: 'b' });
    expect(resolveKey('picker', '', key({ backspace: true }), ctx())).toEqual({ type: 'pickerBackspace' });
  });

  it('Tab and the editing keys do nothing in the picker', () => {
    expect(resolveKey('picker', '', key({ tab: true }), ctx())).toEqual({ type: 'none' });
    expect(resolveKey('picker', 'a', key({ ctrl: true }), ctx())).toEqual({ type: 'none' });
  });
});

describe('resolveKey: mode routing', () => {
  it('every mode maps Enter to a distinct action', () => {
    const modes: KeyMode[] = ['idle', 'running', 'picker'];
    const actions = modes.map((mode) => resolveKey(mode, '', ENTER, ctx()).type);
    expect(actions).toEqual(['submit', 'queue', 'pickerSelect']);
  });
});

describe('cleanText', () => {
  it('removes bracketed-paste markers and normalises line endings', () => {
    expect(cleanText('[200~a\r\nb\rc\x1b[201~')).toBe('a\nb\nc');
  });

  it('drops control characters but keeps newlines', () => {
    expect(cleanText('x\x07y\nz')).toBe('xy\nz');
  });
});
