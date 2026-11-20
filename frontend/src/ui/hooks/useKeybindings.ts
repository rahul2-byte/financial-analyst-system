/**
 * Keybindings. `resolveKey` is pure: Ink's raw `(input, key)` plus
 * the mode and a small context go in, one `Action` comes out. The hook only
 * wires it to `useInput` and keeps the Ctrl+C timer.
 */
import { useInput, type Key } from 'ink';
import { useRef } from 'react';

export type KeyMode = 'idle' | 'running' | 'picker';

/** Second Ctrl+C on an empty composer within this window exits. */
export const EXIT_WINDOW_MS = 1500;

/** Composer editing operations, applied by `composerReducer`. */
export type EditOp =
  | { readonly type: 'insert'; readonly text: string }
  | { readonly type: 'newline' }
  | { readonly type: 'backslashNewline' }
  | { readonly type: 'backspace' }
  | { readonly type: 'left' }
  | { readonly type: 'right' }
  | { readonly type: 'up' }
  | { readonly type: 'down' }
  | { readonly type: 'lineStart' }
  | { readonly type: 'lineEnd' }
  | { readonly type: 'wordLeft' }
  | { readonly type: 'wordRight' }
  | { readonly type: 'deleteWordBack' }
  | { readonly type: 'killToLineStart' };

export type Action =
  | { readonly type: 'none' }
  | { readonly type: 'edit'; readonly op: EditOp }
  | { readonly type: 'submit' }
  | { readonly type: 'queue' }
  | { readonly type: 'complete' }
  | { readonly type: 'completionUp' }
  | { readonly type: 'completionDown' }
  | { readonly type: 'closeCompletion' }
  | { readonly type: 'cancelRun' }
  | { readonly type: 'toggleDetails' }
  | { readonly type: 'clearScreen' }
  | { readonly type: 'clearComposer' }
  | { readonly type: 'armExit' }
  | { readonly type: 'exit' }
  | { readonly type: 'pickerUp' }
  | { readonly type: 'pickerDown' }
  | { readonly type: 'pickerSelect' }
  | { readonly type: 'pickerClose' }
  | { readonly type: 'pickerInsert'; readonly text: string }
  | { readonly type: 'pickerBackspace' };

export interface KeyContext {
  /** The composer has no text. */
  readonly composerEmpty: boolean;
  /** The slash-command completion list is showing. */
  readonly completionOpen: boolean;
  /** The character before the cursor, '' at the start. Used for `\` + Enter. */
  readonly charBeforeCursor: string;
  /** Current time in ms (injectable for tests). */
  readonly now: number;
  /** Time of the last Ctrl+C that armed an exit, or null. */
  readonly lastCtrlCAt: number | null;
}

const NONE: Action = { type: 'none' };

/** Strip bracketed-paste markers and CR line endings from raw input. */
export function cleanText(input: string): string {
  return input
    .replace(/\x1b?\[20[01]~/g, '')
    .replace(/\r\n?/g, '\n')
    .replace(/[\x00-\x09\x0b-\x1f\x7f]/g, '');
}

function isEscapeSequence(input: string): boolean {
  return input.startsWith('\x1b');
}

function insertAction(input: string): Action {
  if (isEscapeSequence(input)) return NONE;
  const text = cleanText(input);
  return text.length > 0 ? { type: 'edit', op: { type: 'insert', text } } : NONE;
}

function resolvePicker(input: string, key: Key): Action {
  if (key.escape || (key.ctrl && input === 'c')) return { type: 'pickerClose' };
  if (key.return) return { type: 'pickerSelect' };
  if (key.upArrow) return { type: 'pickerUp' };
  if (key.downArrow) return { type: 'pickerDown' };
  if (key.backspace || key.delete) return { type: 'pickerBackspace' };
  if (!key.ctrl && !key.meta && !isEscapeSequence(input)) {
    const text = cleanText(input);
    if (text.length > 0) return { type: 'pickerInsert', text };
  }
  return NONE;
}

/**
 * Map one keypress to an action. Every binding maps here; the tests
 * in `test/keybindings.test.tsx` cover each row.
 */
export function resolveKey(mode: KeyMode, input: string, key: Key, ctx: KeyContext): Action {
  if (mode === 'picker') return resolvePicker(input, key);

  const running = mode === 'running';

  // Ctrl+C: cancel while running; clear a non-empty composer; exit on the second
  // press within the window when the composer is empty.
  if (key.ctrl && input === 'c') {
    if (running) return { type: 'cancelRun' };
    if (!ctx.composerEmpty) return { type: 'clearComposer' };
    const armed = ctx.lastCtrlCAt !== null && ctx.now - ctx.lastCtrlCAt <= EXIT_WINDOW_MS;
    return armed ? { type: 'exit' } : { type: 'armExit' };
  }

  if (key.ctrl && input === 'd') {
    return !running && ctx.composerEmpty ? { type: 'exit' } : NONE;
  }

  if (key.escape) {
    if (running) return { type: 'cancelRun' };
    return ctx.completionOpen ? { type: 'closeCompletion' } : NONE;
  }

  // Newline: Shift+Enter, Alt+Enter, `\` + Enter, or Ctrl+J (raw "\n").
  if (key.return) {
    if (key.shift || key.meta) return { type: 'edit', op: { type: 'newline' } };
    if (ctx.charBeforeCursor === '\\') return { type: 'edit', op: { type: 'backslashNewline' } };
    return running ? { type: 'queue' } : { type: 'submit' };
  }
  if (input === '\n' || (key.ctrl && input === 'j')) {
    return { type: 'edit', op: { type: 'newline' } };
  }

  if (key.tab) return { type: 'complete' };

  if (key.upArrow) {
    return ctx.completionOpen ? { type: 'completionUp' } : { type: 'edit', op: { type: 'up' } };
  }
  if (key.downArrow) {
    return ctx.completionOpen ? { type: 'completionDown' } : { type: 'edit', op: { type: 'down' } };
  }

  // Word moves: Alt+←/→ and the Alt+b / Alt+f readline equivalents.
  if (key.meta && key.leftArrow) return { type: 'edit', op: { type: 'wordLeft' } };
  if (key.meta && key.rightArrow) return { type: 'edit', op: { type: 'wordRight' } };
  if (key.meta && input === 'b') return { type: 'edit', op: { type: 'wordLeft' } };
  if (key.meta && input === 'f') return { type: 'edit', op: { type: 'wordRight' } };

  if (key.leftArrow) return { type: 'edit', op: { type: 'left' } };
  if (key.rightArrow) return { type: 'edit', op: { type: 'right' } };
  if (key.home) return { type: 'edit', op: { type: 'lineStart' } };
  if (key.end) return { type: 'edit', op: { type: 'lineEnd' } };

  if (key.ctrl) {
    switch (input) {
      case 'o':
        return { type: 'toggleDetails' };
      case 'l':
        return { type: 'clearScreen' };
      case 'a':
        return { type: 'edit', op: { type: 'lineStart' } };
      case 'e':
        return { type: 'edit', op: { type: 'lineEnd' } };
      case 'w':
        return { type: 'edit', op: { type: 'deleteWordBack' } };
      case 'u':
        return { type: 'edit', op: { type: 'killToLineStart' } };
      default:
        return NONE;
    }
  }

  if (key.backspace || key.delete) return { type: 'edit', op: { type: 'backspace' } };

  if (!key.meta) return insertAction(input);
  return NONE;
}

export interface UseKeybindingsOptions {
  readonly mode: KeyMode;
  /** Read the current composer facts at keypress time (avoids stale closures). */
  readonly getContext: () => Omit<KeyContext, 'now' | 'lastCtrlCAt'>;
  readonly onAction: (action: Action) => void;
  /** Clock for the Ctrl+C window. Defaults to `Date.now`. */
  readonly now?: () => number;
  readonly isActive?: boolean;
}

/** Wire `resolveKey` to Ink's `useInput`. */
export function useKeybindings(options: UseKeybindingsOptions): void {
  const latest = useRef(options);
  latest.current = options;
  const lastCtrlC = useRef<number | null>(null);

  useInput(
    (input, key) => {
      const current = latest.current;
      const now = (current.now ?? Date.now)();
      const action = resolveKey(current.mode, input, key, {
        ...current.getContext(),
        now,
        lastCtrlCAt: lastCtrlC.current,
      });
      if (action.type === 'armExit') lastCtrlC.current = now;
      if (action.type === 'exit') lastCtrlC.current = null;
      if (action.type !== 'none') current.onAction(action);
    },
    { isActive: options.isActive ?? true },
  );
}
