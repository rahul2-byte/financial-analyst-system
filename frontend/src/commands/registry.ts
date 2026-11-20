/**
 * Slash-command registry.
 *
 * Each command says
 * whether it runs locally or calls the bridge, and whether it is refused while
 * a run is active.
 */

export const MODES = ['guided', 'review', 'autonomous'] as const;
export type Mode = (typeof MODES)[number];

export function isMode(value: string | undefined): value is Mode {
  return value !== undefined && (MODES as readonly string[]).includes(value);
}

export type Via = 'local' | 'rpc';

export interface CommandSpec {
  readonly name: string;
  /** Argument hint shown in help and completion, '' when the command takes none. */
  readonly args: string;
  readonly help: string;
  readonly via: Via;
  /** Session and compact commands are refused while a run is active. */
  readonly refuseWhileRunning: boolean;
}

export const RUNNING_REFUSAL = 'Finish or cancel the current run first';

export const COMMANDS: readonly CommandSpec[] = [
  { name: 'help', args: '', help: 'Show commands', via: 'local', refuseWhileRunning: false },
  { name: 'clear', args: '', help: 'Clear the conversation display', via: 'local', refuseWhileRunning: false },
  { name: 'new', args: '', help: 'Start a new conversation', via: 'rpc', refuseWhileRunning: true },
  { name: 'sources', args: '', help: 'Show sources from the last run', via: 'local', refuseWhileRunning: false },
  { name: 'status', args: '', help: 'Show current run status', via: 'local', refuseWhileRunning: false },
  { name: 'debug', args: '', help: 'Show last event and error details', via: 'local', refuseWhileRunning: false },
  { name: 'trace', args: '', help: 'Show the current execution trace', via: 'rpc', refuseWhileRunning: false },
  { name: 'artifact', args: '', help: "Show the last run's artifact path", via: 'local', refuseWhileRunning: false },
  { name: 'logs', args: '', help: 'Show local run artifact location', via: 'local', refuseWhileRunning: false },
  { name: 'mode', args: '[guided|review|autonomous]', help: 'Choose guided, review, or autonomous mode', via: 'local', refuseWhileRunning: false },
  { name: 'context', args: '', help: 'Show context budget and compaction state', via: 'rpc', refuseWhileRunning: false },
  { name: 'compact', args: '', help: 'Compact the current conversation now', via: 'rpc', refuseWhileRunning: true },
  { name: 'sessions', args: '', help: 'List project-local sessions', via: 'rpc', refuseWhileRunning: true },
  { name: 'resume', args: '<id-prefix>', help: 'Resume a saved session by id', via: 'rpc', refuseWhileRunning: true },
  { name: 'history', args: '', help: 'Show the current session transcript', via: 'rpc', refuseWhileRunning: false },
  { name: 'retry', args: '', help: 'Retry the last request', via: 'local', refuseWhileRunning: false },
  { name: 'exit', args: '', help: 'Exit FIN-AI', via: 'local', refuseWhileRunning: false },
];

export const KEY_HELP: readonly string[] = [
  'Enter               submit (while running: queue the prompt)',
  'Shift+Enter, Ctrl+J, \\+Enter   newline',
  'Esc                 close completion · cancel the run',
  'Ctrl+C              clear the composer · cancel the run · twice on an empty composer to exit',
  'Ctrl+D              exit on an empty composer',
  '↑ / ↓               history, or move the completion selection',
  'Tab                 accept completion',
  'Ctrl+O              toggle activity details',
  'Ctrl+L              clear the screen and re-print the transcript',
  'Ctrl+A/E/W/U, Alt+←/→  readline editing',
];

export function findCommand(name: string): CommandSpec | undefined {
  return COMMANDS.find((command) => command.name === name);
}

/** Commands whose name starts with `prefix` (with or without the leading slash). */
export function suggestions(prefix: string): CommandSpec[] {
  const needle = prefix.replace(/^\//, '').toLowerCase();
  return COMMANDS.filter((command) => command.name.startsWith(needle));
}

/**
 * Completion items for the composer value: only while the user is still typing
 * the command name (a leading slash and no space or newline yet).
 */
export function completionFor(value: string): CommandSpec[] {
  if (!value.startsWith('/') || /[\s]/.test(value)) return [];
  return suggestions(value);
}

/** Help text lines for `/help` and the HelpPanel. */
export function helpLines(): string[] {
  const width = 22;
  const commandLines = COMMANDS.map((command) => {
    const usage = command.args ? `/${command.name} ${command.args}` : `/${command.name}`;
    return `${usage.padEnd(width)}${command.help}`;
  });
  return ['Commands', ...commandLines.map((line) => `  ${line}`), '', 'Keys', ...KEY_HELP.map((line) => `  ${line}`)];
}

export interface ParsedCommand {
  /** Command name without the slash; '' when only "/" was typed. */
  readonly name: string;
  readonly args: readonly string[];
  /** The trimmed input, kept for "Unknown command" messages. */
  readonly raw: string;
}

/**
 * shlex-style split: whitespace separates tokens, single quotes are literal,
 * double quotes allow \" and \\, and a backslash escapes the next character
 * outside quotes. Returns null for an unclosed quote.
 */
export function shlexSplit(input: string): string[] | null {
  const out: string[] = [];
  let current = '';
  let hasToken = false;
  let quote: '"' | "'" | null = null;

  for (let i = 0; i < input.length; i += 1) {
    const ch = input.charAt(i);
    if (quote === "'") {
      if (ch === "'") quote = null;
      else current += ch;
      continue;
    }
    if (quote === '"') {
      const next = input.charAt(i + 1);
      if (ch === '"') quote = null;
      else if (ch === '\\' && (next === '"' || next === '\\')) {
        current += next;
        i += 1;
      } else current += ch;
      continue;
    }
    if (ch === "'" || ch === '"') {
      quote = ch;
      hasToken = true;
      continue;
    }
    if (ch === '\\' && i + 1 < input.length) {
      current += input.charAt(i + 1);
      hasToken = true;
      i += 1;
      continue;
    }
    if (/\s/.test(ch)) {
      if (hasToken) {
        out.push(current);
        current = '';
        hasToken = false;
      }
      continue;
    }
    current += ch;
    hasToken = true;
  }

  if (quote !== null) return null;
  if (hasToken) out.push(current);
  return out;
}

/** Parse a composer line. Returns null when it is not a slash command. */
export function parseCommand(text: string): ParsedCommand | null {
  const raw = text.trim();
  if (!raw.startsWith('/')) return null;
  const tokens = shlexSplit(raw.slice(1));
  if (tokens === null || tokens.length === 0) {
    return { name: '', args: [], raw };
  }
  const [name = '', ...args] = tokens;
  return { name, args, raw };
}
