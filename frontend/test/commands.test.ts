import { describe, expect, it, vi } from 'vitest';

import { FakeBridge } from '../src/bridge/fake.js';
import {
  runCommand,
  type AppSnapshot,
  type CommandContext,
  type LastRun,
} from '../src/commands/handlers.js';
import {
  COMMANDS,
  completionFor,
  parseCommand,
  shlexSplit,
  suggestions,
} from '../src/commands/registry.js';
import type { SessionSummary } from '../src/protocol/generated.js';
import type { TranscriptItem } from '../src/state/transcript.js';

const SESSION_A: SessionSummary = {
  id: 'abcd1234-0000-0000-0000-000000000001',
  title: 'Infosys margins',
  message_count: 4,
  run_count: 2,
  last_status: 'completed',
  last_activity: '2026-11-20T10:00:00Z',
};

const SESSION_B: SessionSummary = { ...SESSION_A, id: 'ffff0000-0000-0000-0000-000000000002', title: 'HDFC bank' };

function snapshot(overrides: Partial<AppSnapshot> = {}): AppSnapshot {
  return {
    running: false,
    phase: 'idle',
    latestSequence: 7,
    sessionId: 'sess-1234',
    sessionTitle: 'Research session',
    mode: 'guided',
    model: 'claude-haiku-5-5',
    dataDir: '.finai',
    protocolVersion: 1,
    bridgePid: 4242,
    recentEvents: [{ sequence: 6, type: 'run.completed' }],
    stderrTail: ['bridge warning'],
    ...overrides,
  };
}

function makeContext(options: { running?: boolean; lastRun?: LastRun | null; snap?: Partial<AppSnapshot> } = {}) {
  const bridge = new FakeBridge();
  const printed: TranscriptItem[] = [];
  const spies = {
    clearTranscript: vi.fn(),
    openPicker: vi.fn(),
    setMode: vi.fn(),
    exit: vi.fn(),
    retry: vi.fn(),
  };
  const state = snapshot({ running: options.running ?? false, ...options.snap });
  const ctx: CommandContext = {
    bridge,
    getState: () => state,
    getLastRun: () => options.lastRun ?? null,
    print: (item) => {
      printed.push(item);
    },
    clearTranscript: spies.clearTranscript,
    openPicker: spies.openPicker,
    setMode: spies.setMode,
    exit: spies.exit,
    retry: spies.retry,
  };
  const lines = (): string[] =>
    printed.flatMap((item) => (item.kind === 'command-output' ? [...item.lines] : []));
  return { ctx, bridge, printed, spies, lines };
}

async function run(text: string, options: Parameters<typeof makeContext>[0] = {}) {
  const parsed = parseCommand(text);
  if (parsed === null) throw new Error(`not a command: ${text}`);
  const made = makeContext(options);
  await runCommand(parsed, made.ctx);
  return made;
}

describe('registry', () => {
  it('lists the 17 commands in order', () => {
    expect(COMMANDS.map((command) => command.name)).toEqual([
      'help',
      'clear',
      'new',
      'sources',
      'status',
      'debug',
      'trace',
      'artifact',
      'logs',
      'mode',
      'context',
      'compact',
      'sessions',
      'resume',
      'history',
      'retry',
      'exit',
    ]);
  });

  it('marks RPC commands and the run-refused session commands', () => {
    const rpc = COMMANDS.filter((command) => command.via === 'rpc').map((command) => command.name);
    expect(rpc).toEqual(['new', 'trace', 'context', 'compact', 'sessions', 'resume', 'history']);
    const refused = COMMANDS.filter((command) => command.refuseWhileRunning).map((command) => command.name);
    expect(refused).toEqual(['new', 'compact', 'sessions', 'resume']);
  });

  it('suggests commands by prefix, with or without the slash', () => {
    expect(suggestions('/s').map((command) => command.name)).toEqual(['sources', 'status', 'sessions']);
    expect(suggestions('RE').map((command) => command.name)).toEqual(['resume', 'retry']);
    expect(completionFor('/he').map((command) => command.name)).toEqual(['help']);
    expect(completionFor('/mode review')).toEqual([]);
    expect(completionFor('hello')).toEqual([]);
  });
});

describe('parseCommand and shlexSplit', () => {
  it('returns null for text that is not a command', () => {
    expect(parseCommand('AAPL outlook')).toBeNull();
  });

  it('splits name and arguments', () => {
    expect(parseCommand('  /mode review  ')).toEqual({ name: 'mode', args: ['review'], raw: '/mode review' });
  });

  it('honours single and double quotes and backslash escapes', () => {
    expect(shlexSplit('resume "abc def" \'x y\' a\\ b')).toEqual(['resume', 'abc def', 'x y', 'a b']);
    expect(shlexSplit('"say \\"hi\\""')).toEqual(['say "hi"']);
  });

  it('returns null for an unclosed quote and yields an empty name', () => {
    expect(shlexSplit('resume "abc')).toBeNull();
    expect(parseCommand('/resume "abc')).toEqual({ name: '', args: [], raw: '/resume "abc' });
  });

  it('a lone slash has an empty name', () => {
    expect(parseCommand('/')?.name).toBe('');
  });
});

describe('runCommand', () => {
  it('reports unknown commands and points to /help', async () => {
    const { lines } = await run('/nope');
    expect(lines()).toEqual(['Unknown command /nope — try /help']);
  });

  it('/help prints the command list and keys', async () => {
    const { lines } = await run('/help');
    const text = lines().join('\n');
    expect(text).toContain('/resume <id-prefix>');
    expect(text).toContain('/mode [guided|review|autonomous]');
    expect(text).toContain('Ctrl+O');
  });

  it('/new calls session.new, clears the transcript and prints the header', async () => {
    const { bridge, spies, printed } = await run('/new');
    expect(bridge.calls.map((call) => call.method)).toEqual(['session.new']);
    expect(spies.clearTranscript).toHaveBeenCalledTimes(1);
    expect(printed.some((item) => item.kind === 'header')).toBe(true);
  });

  it('/new while a run is active is refused without calling the bridge', async () => {
    const { bridge, lines } = await run('/new', { running: true });
    expect(bridge.calls).toEqual([]);
    expect(lines()).toEqual(['Finish or cancel the current run first']);
  });

  it('/compact while running is refused', async () => {
    const { bridge, lines } = await run('/compact', { running: true });
    expect(bridge.calls).toEqual([]);
    expect(lines()).toEqual(['Finish or cancel the current run first']);
  });

  it('a bridge -32001 is shown as the same refusal', async () => {
    const made = makeContext();
    made.bridge.setError('context.compact', { code: -32001, message: 'run in progress' });
    await runCommand(parseCommand('/compact')!, made.ctx);
    expect(made.lines()).toEqual(['Finish or cancel the current run first']);
  });

  it('/resume without a prefix shows usage', async () => {
    const { bridge, lines } = await run('/resume');
    expect(bridge.calls).toEqual([]);
    expect(lines()).toEqual(['Usage: /resume <id-prefix>']);
  });

  it('/resume with an ambiguous prefix (-32003) lists the matches', async () => {
    const made = makeContext();
    made.bridge.setError('session.resume', {
      code: -32003,
      message: "Ambiguous session prefix 'ab'",
      data: { matches: [SESSION_A, SESSION_B] },
    });
    await runCommand(parseCommand('/resume ab')!, made.ctx);
    expect(made.lines()).toEqual([
      "Ambiguous session prefix 'ab'",
      '  abcd1234  Infosys margins',
      '  ffff0000  HDFC bank',
      'Use a longer prefix.',
    ]);
  });

  it('/resume success calls session.resume with the prefix', async () => {
    const made = makeContext();
    made.bridge.setResult('session.resume', {
      session: { id: SESSION_A.id, title: SESSION_A.title, message_count: 4, run_count: 2 },
    });
    await runCommand(parseCommand('/resume abcd')!, made.ctx);
    expect(made.bridge.calls).toEqual([{ method: 'session.resume', params: { id_prefix: 'abcd' } }]);
    expect(made.lines().join('\n')).toContain('Resumed session abcd1234 · 4 messages');
  });

  it('/sessions opens the picker with the listed sessions', async () => {
    const made = makeContext();
    made.bridge.setResult('session.list', { sessions: [SESSION_A, SESSION_B] });
    await runCommand(parseCommand('/sessions')!, made.ctx);
    expect(made.bridge.calls).toEqual([{ method: 'session.list', params: { limit: 50 } }]);
    expect(made.spies.openPicker).toHaveBeenCalledWith([SESSION_A, SESSION_B]);
  });

  it('/sessions with nothing saved prints a notice and does not open the picker', async () => {
    const { spies, lines } = await run('/sessions');
    expect(spies.openPicker).not.toHaveBeenCalled();
    expect(lines()).toEqual(['No saved sessions yet.']);
  });

  it('/history lists prior queries, or says there are none', async () => {
    const empty = await run('/history');
    expect(empty.lines()).toEqual(['No prior queries in this session.']);

    const made = makeContext();
    made.bridge.setResult('session.history', { queries: ['AAPL outlook', 'HDFC\nsecond line'] });
    await runCommand(parseCommand('/history')!, made.ctx);
    expect(made.lines()).toEqual(['Session history · 2 queries', '  1. AAPL outlook', '  2. HDFC']);
  });

  it('/mode without an argument shows the current mode; with a valid one it sets it', async () => {
    const shown = await run('/mode');
    expect(shown.lines()).toEqual(['Mode: guided', 'Valid modes: guided, review, autonomous']);

    const set = await run('/mode review');
    expect(set.spies.setMode).toHaveBeenCalledWith('review');
    expect(set.lines()).toEqual(['Mode set to review. It applies to the next run.']);
  });

  it('/mode with an invalid value names the valid modes and does not change anything', async () => {
    const { spies, lines } = await run('/mode turbo');
    expect(spies.setMode).not.toHaveBeenCalled();
    expect(lines()).toEqual(["Invalid mode 'turbo'. Valid modes: guided, review, autonomous"]);
  });

  it('/status prints the phase, sequence, session, bridge pid and protocol', async () => {
    const { lines } = await run('/status');
    expect(lines()).toEqual([
      'FIN-AI · idle · sequence 7',
      '  session      sess-1234',
      '  bridge pid   4242',
      '  protocol     v1',
    ]);
  });

  it('/debug prints the last events and the bridge stderr tail', async () => {
    const { lines } = await run('/debug');
    expect(lines()).toEqual(['Last events', '  #6 run.completed', 'Bridge stderr', '  bridge warning']);
  });

  it('/sources lists the last run sources with hosts, or says there are none', async () => {
    const none = await run('/sources');
    expect(none.lines()).toEqual(['No sources from the last run.']);

    const lastRun: LastRun = {
      query: 'q',
      runId: 'r',
      artifactPath: null,
      sources: [{ label: 'Annual report', url: 'https://example.com/a', host: 'example.com' }],
    };
    const { lines } = await run('/sources', { lastRun });
    expect(lines()).toEqual(['Sources', '  1. Annual report · example.com']);
  });

  it('/artifact shows the last artifact path, or says there is none', async () => {
    const none = await run('/artifact');
    expect(none.lines()).toEqual(['No run artifact in this session yet.']);
    const lastRun: LastRun = { query: 'q', runId: 'r', artifactPath: '/x/run.json', sources: [] };
    const { lines } = await run('/artifact', { lastRun });
    expect(lines()).toEqual(['Run artifact: /x/run.json']);
  });

  it('/logs prints the run artifact directory for the session', async () => {
    const { lines } = await run('/logs');
    expect(lines()).toEqual(['Run artifacts: .finai/sessions/sess-1234/runs/']);
  });

  it('/trace calls trace.tail and prints the ledger and recent records', async () => {
    const made = makeContext();
    made.bridge.setResult('trace.tail', {
      ledger_path: '/ledger.jsonl',
      records: [{ sequence: 3, event_type: 'run.started' }],
    });
    await runCommand(parseCommand('/trace')!, made.ctx);
    expect(made.bridge.calls).toEqual([{ method: 'trace.tail', params: { limit: 12 } }]);
    expect(made.lines()).toEqual(['Trace', '  ledger       /ledger.jsonl', '  events       1', '  #3 run.started']);
  });

  it('/context formats the budget from context.info', async () => {
    const made = makeContext();
    made.bridge.setResult('context.info', {
      message_count: 6,
      estimated_tokens: 500,
      max_tokens: 1000,
      compaction_limit: 800,
    });
    await runCommand(parseCommand('/context')!, made.ctx);
    expect(made.lines()).toEqual([
      'Context',
      '  messages     6',
      '  tokens       ~500 / 1000 (50.0%)',
      '  compact at   800',
    ]);
  });

  it('/compact reports what was compacted, or that there was nothing to do', async () => {
    const none = await run('/compact');
    expect(none.lines()).toEqual(['Nothing to compact.']);

    const made = makeContext();
    made.bridge.setResult('context.compact', { compacted_messages: 3, estimated_tokens: 120 });
    await runCommand(parseCommand('/compact')!, made.ctx);
    expect(made.lines()).toEqual(['Compacted 3 messages · ~120 tokens']);
  });

  it('/new clears the screen and prints a header with the new session title', async () => {
    const made = makeContext();
    made.bridge.setResult('session.new', {
      session: { id: 'new-1', title: 'New research session', message_count: 0, run_count: 0 },
    });
    await runCommand(parseCommand('/new')!, made.ctx);
    const header = made.printed.find((item) => item.kind === 'header');
    expect(header).toEqual({
      kind: 'header',
      id: expect.any(String),
      title: 'New research session',
      mode: 'guided',
      model: 'claude-haiku-5-5',
    });
  });

  it('/retry re-submits through the app, and refuses with no query or while running', async () => {
    const none = await run('/retry');
    expect(none.lines()).toEqual(['Nothing to retry yet.']);
    expect(none.spies.retry).not.toHaveBeenCalled();

    const lastRun: LastRun = { query: 'AAPL', runId: 'r', artifactPath: null, sources: [] };
    const ok = await run('/retry', { lastRun });
    expect(ok.spies.retry).toHaveBeenCalledTimes(1);

    const busy = await run('/retry', { lastRun, running: true });
    expect(busy.spies.retry).not.toHaveBeenCalled();
    expect(busy.lines()).toEqual(['Finish or cancel the current run first']);
  });

  it('/exit calls the exit callback', async () => {
    const { spies } = await run('/exit');
    expect(spies.exit).toHaveBeenCalledTimes(1);
  });

  it('/clear clears the transcript and prints the header again', async () => {
    const { spies, printed } = await run('/clear');
    expect(spies.clearTranscript).toHaveBeenCalledTimes(1);
    expect(printed[0]?.kind).toBe('header');
  });

  it('an unexpected bridge failure is printed as a notice, not thrown', async () => {
    const made = makeContext();
    made.bridge.setError('trace.tail', { code: -32603, message: 'boom' });
    await expect(runCommand(parseCommand('/trace')!, made.ctx)).resolves.toBeUndefined();
    expect(made.lines()).toEqual(['✕ boom']);
  });
});
