/**
 * Slash-command handlers. Each handler prints `command-output`
 * transcript items through `ctx.print`; RPC handlers call the bridge methods on
 * `ctx.bridge`.
 */
import { BridgeError } from '../bridge/client.js';
import type { Bridge } from '../protocol/methods.js';
import type { DisplaySource, SessionSummary } from '../protocol/generated.js';
import { glyphs } from '../render/theme.js';
import type { Phase } from '../state/types.js';
import type { TranscriptItem } from '../state/transcript.js';
import {
  COMMANDS,
  MODES,
  RUNNING_REFUSAL,
  findCommand,
  helpLines,
  isMode,
  type Mode,
  type ParsedCommand,
} from './registry.js';

export interface AppSnapshot {
  readonly running: boolean;
  readonly phase: Phase;
  readonly latestSequence: number;
  readonly sessionId: string | null;
  readonly sessionTitle: string;
  readonly mode: Mode;
  readonly model: string;
  readonly dataDir: string;
  readonly protocolVersion: number;
  readonly bridgePid: number | null;
  /** Most recent events, oldest first (for `/debug`). */
  readonly recentEvents: readonly { readonly sequence: number; readonly type: string }[];
  /** Bridge stderr lines, oldest first (for `/debug`). */
  readonly stderrTail: readonly string[];
}

export interface LastRun {
  readonly query: string | null;
  readonly runId: string | null;
  readonly artifactPath: string | null;
  readonly sources: readonly DisplaySource[];
}

export interface CommandContext {
  readonly bridge: Bridge;
  getState(): AppSnapshot;
  getLastRun(): LastRun | null;
  print(item: TranscriptItem): void;
  clearTranscript(): void;
  openPicker(sessions: readonly SessionSummary[]): void;
  setMode(mode: Mode): void;
  exit(): void;
  /** Re-submit the last query (the app owns the run). */
  retry(): void;
}

let itemCounter = 0;

function nextId(prefix: string): string {
  itemCounter += 1;
  return `${prefix}:${itemCounter}`;
}

function output(ctx: CommandContext, lines: readonly string[]): void {
  ctx.print({ kind: 'command-output', id: nextId('command'), lines });
}

function headerItem(snapshot: AppSnapshot, title: string): TranscriptItem {
  return { kind: 'header', id: nextId('header'), title, mode: snapshot.mode, model: snapshot.model };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function numberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Error text for a failed command. -32001 means a run is active. */
export function errorLines(error: unknown): string[] {
  if (error instanceof BridgeError && error.code === -32001) return [RUNNING_REFUSAL];
  const message = error instanceof Error ? error.message : String(error);
  return [`${glyphs.fail} ${message}`];
}

function formatSessionRow(session: SessionSummary): string {
  return `  ${session.id.slice(0, 8)}  ${session.title}`;
}

const HANDLERS: Record<string, (args: readonly string[], ctx: CommandContext) => Promise<void> | void> = {
  help: (_args, ctx) => {
    output(ctx, helpLines());
  },

  clear: (_args, ctx) => {
    ctx.clearTranscript();
    ctx.print(headerItem(ctx.getState(), ctx.getState().sessionTitle));
  },

  async new(_args, ctx) {
    const result = await ctx.bridge.request('session.new', {});
    ctx.clearTranscript();
    ctx.print(headerItem(ctx.getState(), result.session.title));
  },

  sources: (_args, ctx) => {
    const sources = ctx.getLastRun()?.sources ?? [];
    if (sources.length === 0) {
      output(ctx, ['No sources from the last run.']);
      return;
    }
    const lines = sources.map((source, index) => {
      const host = source.host ?? '';
      const suffix = host && host !== source.label ? ` ${glyphs.dot} ${host}` : '';
      return `  ${index + 1}. ${source.label}${suffix}`;
    });
    output(ctx, ['Sources', ...lines]);
  },

  status: (_args, ctx) => {
    const snapshot = ctx.getState();
    output(ctx, [
      `FIN-AI ${glyphs.dot} ${snapshot.phase} ${glyphs.dot} sequence ${snapshot.latestSequence}`,
      `  session      ${snapshot.sessionId ?? 'none'}`,
      `  bridge pid   ${snapshot.bridgePid ?? 'unknown'}`,
      `  protocol     v${snapshot.protocolVersion}`,
    ]);
  },

  debug: (_args, ctx) => {
    const snapshot = ctx.getState();
    const events = snapshot.recentEvents.slice(-20);
    const stderr = snapshot.stderrTail.slice(-40);
    output(ctx, [
      'Last events',
      ...(events.length > 0 ? events.map((event) => `  #${event.sequence} ${event.type}`) : ['  (none)']),
      'Bridge stderr',
      ...(stderr.length > 0 ? stderr.map((line) => `  ${line}`) : ['  (none)']),
    ]);
  },

  async trace(_args, ctx) {
    const result = await ctx.bridge.request('trace.tail', { limit: 12 });
    const records: readonly Record<string, unknown>[] = result.records;
    output(ctx, [
      'Trace',
      `  ledger       ${result.ledger_path}`,
      `  events       ${records.length}`,
      ...records.slice(-12).map((record) => `  #${String(record.sequence ?? '?')} ${String(record.event_type ?? '?')}`),
    ]);
  },

  artifact: (_args, ctx) => {
    const path = ctx.getLastRun()?.artifactPath;
    output(ctx, [path ? `Run artifact: ${path}` : 'No run artifact in this session yet.']);
  },

  logs: (_args, ctx) => {
    const snapshot = ctx.getState();
    output(ctx, [`Run artifacts: ${snapshot.dataDir}/sessions/${snapshot.sessionId ?? 'none'}/runs/`]);
  },

  mode: (args, ctx) => {
    const [value] = args;
    if (value === undefined) {
      output(ctx, [`Mode: ${ctx.getState().mode}`, `Valid modes: ${MODES.join(', ')}`]);
      return;
    }
    if (!isMode(value)) {
      output(ctx, [`Invalid mode '${value}'. Valid modes: ${MODES.join(', ')}`]);
      return;
    }
    ctx.setMode(value);
    output(ctx, [`Mode set to ${value}. It applies to the next run.`]);
  },

  async context(_args, ctx) {
    const info = await ctx.bridge.request('context.info', {});
    const messages = numberField(info, 'message_count');
    const estimated = numberField(info, 'estimated_tokens');
    const max = numberField(info, 'max_tokens');
    const compactAt = numberField(info, 'compaction_limit');
    const compacted = numberField(info, 'compacted_messages');
    if (messages === null && estimated === null) {
      output(ctx, ['Context', '  unavailable']);
      return;
    }
    const percent = estimated !== null && max ? ((100 * estimated) / max).toFixed(1) : '0.0';
    const lines = [
      'Context',
      `  messages     ${messages ?? 0}`,
      `  tokens       ~${estimated ?? 0} / ${max ?? 0} (${percent}%)`,
      `  compact at   ${compactAt ?? 'unknown'}`,
    ];
    if (compacted) lines.push(`  last compact ${compacted} messages`);
    output(ctx, lines);
  },

  async compact(_args, ctx) {
    const result = await ctx.bridge.request('context.compact', {});
    const compacted = numberField(result, 'compacted_messages');
    const estimated = numberField(result, 'estimated_tokens');
    if (!compacted) {
      output(ctx, ['Nothing to compact.']);
      return;
    }
    output(ctx, [`Compacted ${compacted} messages${estimated !== null ? ` · ~${estimated} tokens` : ''}`]);
  },

  async sessions(_args, ctx) {
    const result = await ctx.bridge.request('session.list', { limit: 50 });
    if (result.sessions.length === 0) {
      output(ctx, ['No saved sessions yet.']);
      return;
    }
    ctx.openPicker(result.sessions);
  },

  async resume(args, ctx) {
    const [prefix] = args;
    if (prefix === undefined) {
      output(ctx, ['Usage: /resume <id-prefix>']);
      return;
    }
    try {
      const result = await ctx.bridge.request('session.resume', { id_prefix: prefix });
      ctx.clearTranscript();
      ctx.print(headerItem(ctx.getState(), result.session.title));
      output(
        ctx,
        [`Resumed session ${result.session.id.slice(0, 8)} ${glyphs.dot} ${result.session.message_count} messages`],
      );
    } catch (error) {
      if (error instanceof BridgeError && error.code === -32003) {
        const matches = isRecord(error.data) && Array.isArray(error.data.matches)
          ? (error.data.matches as SessionSummary[])
          : [];
        output(ctx, [
          error.message,
          ...matches.map(formatSessionRow),
          ...(matches.length > 0 ? ['Use a longer prefix.'] : []),
        ]);
        return;
      }
      throw error;
    }
  },

  async history(_args, ctx) {
    const result = await ctx.bridge.request('session.history', {});
    const queries = result.queries;
    if (queries.length === 0) {
      output(ctx, ['No prior queries in this session.']);
      return;
    }
    output(ctx, [
      `Session history ${glyphs.dot} ${queries.length} queries`,
      ...queries.map((query, index) => `  ${index + 1}. ${(query.split('\n')[0] ?? '').slice(0, 100)}`),
    ]);
  },

  retry(_args, ctx) {
    if (ctx.getState().running) {
      output(ctx, [RUNNING_REFUSAL]);
      return;
    }
    if (!ctx.getLastRun()?.query) {
      output(ctx, ['Nothing to retry yet.']);
      return;
    }
    ctx.retry();
  },

  exit: (_args, ctx) => {
    ctx.exit();
  },
};

/**
 * Run one parsed slash command. Errors from the bridge are printed as notices,
 * never thrown, so the composer keeps working.
 */
export async function runCommand(command: ParsedCommand, ctx: CommandContext): Promise<void> {
  const spec = findCommand(command.name);
  if (spec === undefined) {
    const label = command.name || command.raw.replace(/^\//, '');
    output(ctx, [`Unknown command /${label} — try /help`]);
    return;
  }
  if (spec.refuseWhileRunning && ctx.getState().running) {
    output(ctx, [RUNNING_REFUSAL]);
    return;
  }
  const handler = HANDLERS[spec.name];
  if (handler === undefined) {
    output(ctx, [`Unknown command /${command.name} — try /help`]);
    return;
  }
  try {
    await handler(command.args, ctx);
  } catch (error) {
    output(ctx, errorLines(error));
  }
}

/** Command names that have a handler (kept in step with COMMANDS). */
export const HANDLED_COMMANDS: readonly string[] = COMMANDS.map((command) => command.name);
