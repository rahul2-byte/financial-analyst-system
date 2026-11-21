/**
 * Multi-line composer. The editor state lives in
 * `composerReducer`, a pure function, so the editing rules are tested without
 * a terminal. The component applies keypresses through `useKeybindings`.
 */
import { Box, Text } from 'ink';
import { memo, useRef, useState } from 'react';

import { completionFor, type CommandSpec } from '../commands/registry.js';
import { color, glyphs } from '../render/theme.js';
import { useKeybindings, type Action, type EditOp, type KeyMode } from './hooks/useKeybindings.js';
import { Completion } from './Completion.js';

export const PLACEHOLDER = 'Ask about a stock, or / for commands';

export interface ComposerState {
  readonly value: string;
  /** Cursor as a UTF-16 index into `value`, 0..value.length. */
  readonly cursor: number;
  /** Submitted prompts, oldest first. */
  readonly history: readonly string[];
  /** Index into `history` while browsing with ↑/↓, null when editing a fresh line. */
  readonly historyIndex: number | null;
  /** The unsent text saved when history browsing starts. */
  readonly draft: string;
  readonly completionIndex: number;
  /** Set by Esc to hide the completion list until the text changes again. */
  readonly dismissed: boolean;
}

export type ComposerKey =
  | EditOp
  | { readonly type: 'set'; readonly value: string }
  | { readonly type: 'clear' }
  | { readonly type: 'submitted' }
  | { readonly type: 'completionMove'; readonly delta: 1 | -1; readonly count: number }
  | { readonly type: 'dismiss' };

export function initialComposerState(history: readonly string[] = []): ComposerState {
  return {
    value: '',
    cursor: 0,
    history,
    historyIndex: null,
    draft: '',
    completionIndex: 0,
    dismissed: false,
  };
}

const isHighSurrogate = (code: number): boolean => code >= 0xd800 && code <= 0xdbff;
const isLowSurrogate = (code: number): boolean => code >= 0xdc00 && code <= 0xdfff;

function prevIndex(value: string, cursor: number): number {
  if (cursor <= 0) return 0;
  if (cursor >= 2 && isLowSurrogate(value.charCodeAt(cursor - 1)) && isHighSurrogate(value.charCodeAt(cursor - 2))) {
    return cursor - 2;
  }
  return cursor - 1;
}

function nextIndex(value: string, cursor: number): number {
  if (cursor >= value.length) return value.length;
  if (isHighSurrogate(value.charCodeAt(cursor)) && isLowSurrogate(value.charCodeAt(cursor + 1))) {
    return cursor + 2;
  }
  return cursor + 1;
}

/** Index of the first character of the line containing `cursor`. */
export function lineStartOf(value: string, cursor: number): number {
  if (cursor <= 0) return 0;
  return value.lastIndexOf('\n', cursor - 1) + 1;
}

/** Index of the newline ending the line containing `cursor`, or value.length. */
export function lineEndOf(value: string, cursor: number): number {
  const newline = value.indexOf('\n', cursor);
  return newline === -1 ? value.length : newline;
}

/** Zero-based line number of `cursor`. */
export function lineIndexOf(value: string, cursor: number): number {
  let count = 0;
  for (let i = 0; i < cursor && i < value.length; i += 1) {
    if (value.charAt(i) === '\n') count += 1;
  }
  return count;
}

function moveVertical(value: string, cursor: number, direction: -1 | 1): number {
  const column = cursor - lineStartOf(value, cursor);
  if (direction === -1) {
    const previousEnd = lineStartOf(value, cursor) - 1;
    const previousStart = lineStartOf(value, previousEnd);
    return previousStart + Math.min(column, previousEnd - previousStart);
  }
  const nextStart = lineEndOf(value, cursor) + 1;
  const nextEnd = lineEndOf(value, nextStart);
  return nextStart + Math.min(column, nextEnd - nextStart);
}

function wordLeftIndex(value: string, cursor: number): number {
  let i = cursor;
  while (i > 0 && /\s/.test(value.charAt(i - 1))) i -= 1;
  while (i > 0 && !/\s/.test(value.charAt(i - 1))) i -= 1;
  return i;
}

function wordRightIndex(value: string, cursor: number): number {
  let i = cursor;
  while (i < value.length && /\s/.test(value.charAt(i))) i += 1;
  while (i < value.length && !/\s/.test(value.charAt(i))) i += 1;
  return i;
}

/** Replace the value. Changing the text resets the completion selection and dismissal. */
function withValue(state: ComposerState, value: string, cursor: number): ComposerState {
  if (value === state.value) return { ...state, cursor };
  return { ...state, value, cursor, completionIndex: 0, dismissed: false };
}

function historyPrev(state: ComposerState): ComposerState {
  if (state.history.length === 0) return state;
  const index = state.historyIndex === null ? state.history.length - 1 : Math.max(0, state.historyIndex - 1);
  const value = state.history[index] ?? '';
  return {
    ...state,
    value,
    cursor: value.length,
    historyIndex: index,
    draft: state.historyIndex === null ? state.value : state.draft,
    completionIndex: 0,
    dismissed: false,
  };
}

function historyNext(state: ComposerState): ComposerState {
  if (state.historyIndex === null) return state;
  if (state.historyIndex < state.history.length - 1) {
    const index = state.historyIndex + 1;
    const value = state.history[index] ?? '';
    return { ...state, value, cursor: value.length, historyIndex: index, completionIndex: 0, dismissed: false };
  }
  return {
    ...state,
    value: state.draft,
    cursor: state.draft.length,
    historyIndex: null,
    draft: '',
    completionIndex: 0,
    dismissed: false,
  };
}

/**
 * Apply one editing key to the composer state. Pure: no I/O, no clock.
 *
 * ↑ and ↓ move the cursor between lines first and browse history only from the
 * first or last line. `submitted` records the text in history and clears it.
 */
export function composerReducer(state: ComposerState, key: ComposerKey): ComposerState {
  const { value, cursor } = state;
  switch (key.type) {
    case 'insert': {
      const next = value.slice(0, cursor) + key.text + value.slice(cursor);
      return withValue(state, next, cursor + key.text.length);
    }
    case 'newline':
      return withValue(state, value.slice(0, cursor) + '\n' + value.slice(cursor), cursor + 1);
    case 'backslashNewline': {
      if (cursor > 0 && value.charAt(cursor - 1) === '\\') {
        return withValue(state, value.slice(0, cursor - 1) + '\n' + value.slice(cursor), cursor);
      }
      return withValue(state, value.slice(0, cursor) + '\n' + value.slice(cursor), cursor + 1);
    }
    case 'backspace': {
      if (cursor === 0) return state;
      const start = prevIndex(value, cursor);
      return withValue(state, value.slice(0, start) + value.slice(cursor), start);
    }
    case 'left':
      return { ...state, cursor: prevIndex(value, cursor) };
    case 'right':
      return { ...state, cursor: nextIndex(value, cursor) };
    case 'up':
      if (lineStartOf(value, cursor) === 0) return historyPrev(state);
      return { ...state, cursor: moveVertical(value, cursor, -1) };
    case 'down':
      if (lineEndOf(value, cursor) === value.length) return historyNext(state);
      return { ...state, cursor: moveVertical(value, cursor, 1) };
    case 'lineStart':
      return { ...state, cursor: lineStartOf(value, cursor) };
    case 'lineEnd':
      return { ...state, cursor: lineEndOf(value, cursor) };
    case 'wordLeft':
      return { ...state, cursor: wordLeftIndex(value, cursor) };
    case 'wordRight':
      return { ...state, cursor: wordRightIndex(value, cursor) };
    case 'deleteWordBack': {
      const start = wordLeftIndex(value, cursor);
      return withValue(state, value.slice(0, start) + value.slice(cursor), start);
    }
    case 'killToLineStart': {
      const start = lineStartOf(value, cursor);
      return withValue(state, value.slice(0, start) + value.slice(cursor), start);
    }
    case 'set':
      return withValue(state, key.value, key.value.length);
    case 'clear':
      return { ...state, value: '', cursor: 0, historyIndex: null, draft: '', completionIndex: 0, dismissed: false };
    case 'submitted': {
      const history = value.trim() !== '' && state.history.at(-1) !== value ? [...state.history, value] : state.history;
      return { ...initialComposerState(history) };
    }
    case 'completionMove': {
      if (key.count <= 0) return state;
      const index = (((state.completionIndex + key.delta) % key.count) + key.count) % key.count;
      return { ...state, completionIndex: index };
    }
    case 'dismiss':
      return { ...state, dismissed: true };
  }
}

/** Completion rows for the current state (empty when hidden). */
export function visibleCompletion(state: ComposerState): readonly CommandSpec[] {
  return state.dismissed ? [] : completionFor(state.value);
}

function CursorLine({ line, column }: { line: string; column: number | null }) {
  if (column === null) return <Text>{line === '' ? ' ' : line}</Text>;
  const before = line.slice(0, column);
  const rest = line.slice(column);
  const first = Array.from(rest)[0] ?? ' ';
  const after = rest.slice(first.length);
  return (
    <Text>
      {before}
      <Text inverse>{first}</Text>
      {after}
    </Text>
  );
}

export interface ComposerProps {
  /** `running` queues a submitted prompt and keeps the composer editable. */
  readonly mode: 'idle' | 'running';
  /** Prior prompts for ↑/↓ browsing, oldest first. Read once at mount. */
  readonly history?: readonly string[];
  readonly onSubmit: (text: string, intent: 'submit' | 'queue') => void;
  /** App-level actions: cancelRun, toggleDetails, clearScreen, armExit, exit. */
  readonly onAction?: (action: Action) => void;
  readonly now?: () => number;
  readonly isActive?: boolean;
}

export const Composer = memo(function Composer(props: ComposerProps) {
  const [state, setState] = useState<ComposerState>(() => initialComposerState(props.history ?? []));
  // Keypresses can arrive faster than React re-renders, so the handler reads
  // and writes this ref instead of the rendered state.
  const stateRef = useRef(state);

  const commit = (key: ComposerKey): void => {
    const next = composerReducer(stateRef.current, key);
    stateRef.current = next;
    setState(next);
  };

  const onAction = (action: Action): void => {
    const current = stateRef.current;
    const items = visibleCompletion(current);
    switch (action.type) {
      case 'edit':
        commit(action.op);
        return;
      case 'submit':
      case 'queue': {
        const text = current.value;
        if (text.trim() === '') return;
        commit({ type: 'submitted' });
        props.onSubmit(text, action.type === 'queue' ? 'queue' : 'submit');
        return;
      }
      case 'complete': {
        const chosen = items[current.completionIndex % Math.max(items.length, 1)];
        if (chosen !== undefined) commit({ type: 'set', value: `/${chosen.name} ` });
        return;
      }
      case 'completionUp':
        commit({ type: 'completionMove', delta: -1, count: items.length });
        return;
      case 'completionDown':
        commit({ type: 'completionMove', delta: 1, count: items.length });
        return;
      case 'closeCompletion':
        commit({ type: 'dismiss' });
        return;
      case 'clearComposer':
        commit({ type: 'clear' });
        return;
      default:
        props.onAction?.(action);
    }
  };

  const mode: KeyMode = props.mode;
  useKeybindings({
    mode,
    getContext: () => {
      const current = stateRef.current;
      return {
        composerEmpty: current.value.length === 0,
        completionOpen: visibleCompletion(current).length > 0,
        charBeforeCursor: current.cursor > 0 ? current.value.charAt(current.cursor - 1) : '',
      };
    },
    onAction,
    ...(props.now !== undefined ? { now: props.now } : {}),
    ...(props.isActive !== undefined ? { isActive: props.isActive } : {}),
  });

  const items = visibleCompletion(state);
  const selected = items.length > 0 ? state.completionIndex % items.length : 0;
  const cursorLine = lineIndexOf(state.value, state.cursor);
  const column = state.cursor - lineStartOf(state.value, state.cursor);
  const lines = state.value.split('\n');

  return (
    <Box flexDirection="column">
      <Box
        flexDirection="column"
        borderStyle="single"
        borderColor={color('rule')}
        borderTop
        borderBottom={false}
        borderLeft={false}
        borderRight={false}
      >
        {state.value === '' ? (
          <Text>
            <Text color={color('ledger')}>{glyphs.prompt} </Text>
            <Text inverse> </Text>
            <Text color={color('dim')}>{PLACEHOLDER}</Text>
          </Text>
        ) : (
          lines.map((line, index) => (
            <Box key={index}>
              <Text color={color('ledger')}>{index === 0 ? `${glyphs.prompt} ` : '  '}</Text>
              <CursorLine line={line} column={index === cursorLine ? column : null} />
            </Box>
          ))
        )}
      </Box>
      <Completion items={items} selected={selected} />
    </Box>
  );
});
