/**
 * The interactive app. Committed transcript items go to Ink's
 * `<Static>` (scrollback); a small live region shows the active run; the composer,
 * the session picker and the help panel sit below it.
 *
 * Run handling lives in `RunCollector`: it feeds each `run.event` into a fresh
 * presentation store and turns the store's state into transcript items.
 */
import { Box, Static, Text, useApp, useInput, useStdout } from 'ink';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';

import type {
  Display,
  DisplayCandidate,
  DisplaySource,
  InitializeResult,
  ReportView,
  ResearchEvent,
  RunEventParams,
  RunFinishedParams,
  RunStartParams,
  SessionInfo,
  SessionSummary,
} from '../protocol/generated.js';
import type { Bridge, MethodName, RequestOptions } from '../protocol/methods.js';
import { PROTOCOL_VERSION } from '../protocol/version.js';
import { runCommand, type AppSnapshot, type CommandContext, type LastRun } from '../commands/handlers.js';
import { isMode, parseCommand, type Mode } from '../commands/registry.js';
import { humanLabel, isRawToolId, SPINNER_FRAMES } from '../render/format.js';
import { color } from '../render/theme.js';
import {
  createPresentationStore,
  type PresentationAction,
  type Store,
} from '../state/store.js';
import type { ActivityState, PresentationState, Phase } from '../state/types.js';
import {
  activityTrailItem,
  commitFinal,
  describeFailure,
  commitStreamingText,
  runFooterItem,
  sourcesItem,
  startDraft,
  userItem,
  type TrailRow,
  type TranscriptItem,
} from '../state/transcript.js';
import { ActivityTrail } from './ActivityTrail.js';
import { ClippedTail } from './ClippedTail.js';
import { parseReport } from './report/parse.js';
import { Composer } from './Composer.js';
import { HelpPanel } from './HelpPanel.js';
import { LiveActivity } from './LiveActivity.js';
import { type Action } from './hooks/useKeybindings.js';
import { useElapsed } from './hooks/useElapsed.js';
import { useBridge, type BridgeHandle, type BridgeLaunch, type CrashReport } from './hooks/useBridge.js';
import { SessionPicker } from './SessionPicker.js';
import { StatusLine } from './StatusLine.js';
import { StreamingAnswer } from './StreamingAnswer.js';
import { TranscriptItemView } from './TranscriptItemView.js';

const NOTICE_MS = 1500;
const RECENT_EVENT_LIMIT = 50;
const STDERR_LINES = 40;

let runCounter = 0;

/** Client-side run id: unique within this UI process. */
export function newRunId(now: number = Date.now()): string {
  runCounter += 1;
  return `tui-${now.toString(36)}-${runCounter}`;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function isCancelled(status: string): boolean {
  return status === 'cancelled' || status === 'canceled';
}

// ---------------------------------------------------------------------------
// Run collection
// ---------------------------------------------------------------------------

export interface RunCollectorOptions {
  readonly clientRunId: string;
  readonly query: string;
  readonly store: Store<PresentationState, PresentationAction>;
  readonly now?: () => number;
}

/**
 * Turns one run's events into transcript items. The store holds the reduced state;
 * the collector only decides what to commit and when. Commit order follows
 * transcript.ts: trail → answer chunks → sources → clarification/notice → footer.
 */
export class RunCollector {
  readonly clientRunId: string;
  readonly query: string;
  readonly store: Store<PresentationState, PresentationAction>;
  readonly startedAt: number;
  readonly #now: () => number;
  #report: ReportView | null = null;
  #sources: readonly DisplaySource[] = [];
  #sourceKeys = new Set<string>();
  #candidates: readonly DisplayCandidate[] = [];
  #lines: readonly string[] = [];
  #failedNouns: readonly string[] = [];
  /** Display labels for tools, keyed like `state.activeTools` (tool_id, else tool name). */
  readonly #toolLabels = new Map<string, string>();
  #artifactPath: string | null = null;
  #finished = false;
  #limited = false;
  #unavailable: readonly string[] = [];
  /** Raw failure messages seen during the run, newest last. */
  readonly #failures: string[] = [];
  #trail: { toolCount: number; rows: readonly TrailRow[] } | null = null;

  constructor(options: RunCollectorOptions) {
    this.clientRunId = options.clientRunId;
    this.query = options.query;
    this.store = options.store;
    this.#now = options.now ?? Date.now;
    this.startedAt = this.#now();
  }

  get finished(): boolean {
    return this.#finished;
  }

  get sources(): readonly DisplaySource[] {
    return this.#sources;
  }

  get failedNouns(): readonly string[] {
    return this.#failedNouns;
  }

  get artifactPath(): string | null {
    return this.#artifactPath;
  }

  /** The tool lines of the finished run, for Ctrl+O when idle. */
  get lastTrail(): { toolCount: number; failedNouns: readonly string[]; rows: readonly TrailRow[] } | null {
    return this.#trail === null ? null : { ...this.#trail, failedNouns: this.#failedNouns };
  }

  /**
   * The answer streamed so far. Nothing is committed to scrollback while a run is active
   *: the whole draft stays in the live region, and `run.finished` commits either
   * the structured report or the Markdown answer, once.
   */
  liveText(text: string): string {
    return text;
  }

  /**
   * What the live region shows. The reducer keeps raw tool ids (`data:fetch_fundamentals`),
   * which `humanLabel` hides, so the display label from the same event replaces them.
   */
  liveActivities(state: PresentationState): {
    operation: string | null;
    activities: Readonly<Record<string, ActivityState>>;
  } {
    const activities: Record<string, ActivityState> = { ...state.activities };
    for (const [name, activity] of Object.entries(activities)) {
      if (!name.startsWith('tool:')) continue;
      const label = this.#toolLabels.get(name.slice('tool:'.length));
      if (label !== undefined) activities[name] = { ...activity, label };
    }
    const current = state.currentOperation;
    const last = state.activeTools[state.activeTools.length - 1];
    const labelled = last === undefined ? undefined : this.#toolLabels.get(last);
    const operation = current !== null && isRawToolId(current) && labelled !== undefined ? labelled : current;
    return { operation, activities };
  }

  onEvent(event: ResearchEvent, display: Display | null): TranscriptItem[] {
    this.store.dispatch({ type: 'event', event, display });
    this.#absorb(display);
    this.#absorbToolLabel(event, display);
    return [];
  }

  onFinished(params: RunFinishedParams): TranscriptItem[] {
    const artifact = typeof params.artifact_path === 'string' ? params.artifact_path : null;
    const availability = Array.isArray(params.evidence_availability) ? params.evidence_availability : [];
    this.#unavailable = availability
      .filter((entry) => entry.status !== 'available')
      .map((entry) => String(entry.name).toLowerCase());
    this.#limited = params.evidence_status === 'limited';
    this.#report = String(params.outcome) === 'completed' ? parseReport(params.report) : null;
    return this.#finish(String(params.outcome), String(params.message ?? ''), artifact);
  }

  /** End the run locally (bridge crash, failed run.start). No-op after a normal finish. */
  abort(status: string, message: string): TranscriptItem[] {
    return this.#finish(status, message, null);
  }

  #absorb(display: Display | null): void {
    if (!display) return;
    if (Array.isArray(display.sources)) {
      // Each sources.updated carries only that tool's sources: accumulate and dedupe by
      // (url, label), the same key state.py / the reducer use.
      for (const source of display.sources as DisplaySource[]) {
        const key = JSON.stringify([source.url ?? '', source.label ?? '']);
        if (this.#sourceKeys.has(key)) continue;
        this.#sourceKeys.add(key);
        this.#sources = [...this.#sources, source];
      }
    }
    if (Array.isArray(display.candidates)) this.#candidates = display.candidates as DisplayCandidate[];
    if (Array.isArray(display.lines)) this.#lines = display.lines as string[];
    if (Array.isArray(display.failed_nouns)) this.#failedNouns = display.failed_nouns as string[];
    if (typeof display.friendly === 'string' && display.friendly !== '') this.#failures.push(display.friendly);
    if (typeof display.notice === 'string' && display.notice !== '') this.#failures.push(display.notice);
  }

  #absorbToolLabel(event: ResearchEvent, display: Display | null): void {
    if (!display || typeof display.label !== 'string' || display.label.trim() === '') return;
    const tool = event as { tool?: unknown; tool_id?: unknown };
    if (typeof tool.tool !== 'string') return;
    const key = typeof tool.tool_id === 'string' && tool.tool_id !== '' ? tool.tool_id : tool.tool;
    this.#toolLabels.set(key, display.label);
  }

  #trailItem(state: PresentationState): TranscriptItem {
    return activityTrailItem(
      this.clientRunId,
      state,
      this.#failedNouns,
      true,
      this.liveActivities(state).activities,
    );
  }

  #finish(status: string, message: string, artifactPath: string | null): TranscriptItem[] {
    if (this.#finished) return [];
    this.#finished = true;
    this.#artifactPath = artifactPath;
    const id = this.clientRunId;
    const state = this.store.getState();
    const text = state.responseText;
    const toolCount = Object.keys(state.activities).filter((key) => key.startsWith('tool:')).length;

    const trailItem = this.#trailItem(state);
    if (trailItem.kind === 'activity-trail') this.#trail = { toolCount: trailItem.toolCount, rows: trailItem.rows };

    const failed = status === 'failed' || status === 'error';
    const cancelled = isCancelled(status);
    const failure = failed ? describeFailure([message, ...this.#failures.slice().reverse()]) : null;

    const closing: TranscriptItem[] = [];
    if (this.#candidates.length > 0 || this.#lines.length > 0) {
      closing.push({
        kind: 'clarification',
        id: `${id}:clarification`,
        runId: id,
        candidates: this.#candidates,
        lines: this.#lines,
      });
    } else if (status !== 'completed') {
      closing.push({
        kind: 'notice',
        id: `${id}:notice`,
        runId: id,
        tone: cancelled ? 'dim' : 'loss',
        text: cancelled
          ? 'Cancelled. Send /retry to run it again.'
          : (failure?.notice ?? `Run ${status}. Try /retry.`),
      });
    }

    // Partial = finished, but some evidence was unavailable. A failed or cancelled run is not partial.
    const unavailable =
      this.#unavailable.length > 0
        ? this.#unavailable
        : this.#failedNouns.map((noun) => humanLabel(noun)?.toLowerCase()).filter((n): n is string => !!n);
    const partial = status === 'completed' && (this.#limited || unavailable.length > 0);

    // A structured report replaces the prose and carries its own sources; otherwise the
    // Markdown answer commits as before. Either way it is one commit, at the end.
    const report = this.#report;
    const sourceCount = report ? Math.max(this.#sources.length, report.sources?.length ?? 0) : this.#sources.length;
    const result = commitFinal(startDraft(id), report ? '' : text, {
      trail: () => trailItem,
      closing,
      sources: report ? null : sourcesItem(id, this.#sources),
      footer: runFooterItem(id, {
        status,
        elapsedMs: this.#now() - this.startedAt,
        toolCount,
        sourceCount,
        partial,
        unavailable: partial ? unavailable : [],
        reason: failure?.reason ?? null,
      }),
    });
    if (report) {
      const at = result.items.findIndex((item) => item.kind === 'activity-trail') + 1;
      result.items.splice(at, 0, { kind: 'report', id: `${id}:report`, runId: id, report });
    }
    this.store.flushNow();
    return result.items;
  }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export interface AppProps {
  readonly launch: BridgeLaunch;
  /** A ready-made bridge for snapshots and tests; no process is spawned. */
  readonly injected?: Bridge;
}

interface SessionRef {
  id: string | null;
  title: string;
  model: string;
  dataDir: string;
}

export function App({ launch, injected }: AppProps) {
  const { exit } = useApp();
  const { stdout } = useStdout();
  const width = Math.max(20, stdout?.columns ?? 80);

  const [committed, setCommitted] = useState<TranscriptItem[]>([]);
  const [epoch, setEpoch] = useState(0);
  const [runStore, setRunStore] = useState(() => createPresentationStore());
  const state = useSyncExternalStore(runStore.subscribe, runStore.getState);
  const [running, setRunning] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [queuedCount, setQueuedCount] = useState(0);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [picker, setPicker] = useState<readonly SessionSummary[] | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [mode, setModeState] = useState<Mode>(launch.mode && isMode(launch.mode) ? launch.mode : 'guided');
  const [sessionTitle, setSessionTitle] = useState('');
  const [modelId, setModelId] = useState('');

  const elapsed = useElapsed(running, runStartedAt);

  const modeRef = useRef<Mode>(mode);
  const runningRef = useRef(false);
  const queueRef = useRef<string[]>([]);
  const collectorRef = useRef<RunCollector | null>(null);
  const storeRef = useRef<Store<PresentationState, PresentationAction>>(runStore);
  const lastRunRef = useRef<LastRun | null>(null);
  const lastTrailRef = useRef<{
    runId: string;
    toolCount: number;
    failedNouns: readonly string[];
    rows: readonly TrailRow[];
  } | null>(null);
  const sessionRef = useRef<SessionRef>({ id: null, title: '', model: '', dataDir: launch.dataDir ?? '.finai' });
  const recentRef = useRef<{ sequence: number; type: string }[]>([]);
  const clientRef = useRef<Bridge | null>(null);
  const bridgeRef = useRef<BridgeHandle | null>(null);
  const headerShownRef = useRef(false);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pushItems = (items: readonly TranscriptItem[]): void => {
    if (items.length > 0) setCommitted((prev) => [...prev, ...items]);
  };

  const flashNotice = (text: string): void => {
    setNotice(text);
    if (noticeTimer.current !== null) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), NOTICE_MS);
  };

  useEffect(
    () => () => {
      if (noticeTimer.current !== null) clearTimeout(noticeTimer.current);
    },
    [],
  );

  const recordEvent = (event: { sequence: number; type: string }): void => {
    const next = [...recentRef.current, event];
    recentRef.current = next.length > RECENT_EVENT_LIMIT ? next.slice(-RECENT_EVENT_LIMIT) : next;
  };

  const endRun = (collector: RunCollector): void => {
    if (collectorRef.current !== collector) return;
    collectorRef.current = null;
    lastRunRef.current = {
      query: collector.query,
      runId: collector.clientRunId,
      artifactPath: collector.artifactPath,
      sources: collector.sources,
    };
    const trail = collector.lastTrail;
    lastTrailRef.current = trail === null ? null : { runId: collector.clientRunId, ...trail };
    runningRef.current = false;
    setRunning(false);
    setRunStartedAt(null);
    const next = queueRef.current.shift();
    setQueuedCount(queueRef.current.length);
    if (next !== undefined) startRun(next);
  };

  const bridge = useBridge({
    launch,
    injected,
    onConnected: (client, info: InitializeResult) => {
      clientRef.current = client;
      const session: SessionInfo = info.session;
      const model = info.model?.id ?? '';
      sessionRef.current = {
        id: session.id,
        title: session.title,
        model,
        dataDir: String(info.data_dir),
      };
      setSessionTitle(session.title);
      setModelId(model);
      if (!launch.mode && isMode(String(info.mode))) {
        modeRef.current = info.mode as Mode;
        setModeState(info.mode as Mode);
      }
      if (!headerShownRef.current) {
        headerShownRef.current = true;
        pushItems([
          { kind: 'header', id: 'header:start', title: session.title, mode: modeRef.current, model },
        ]);
      }
      client.on('run.event', (params: RunEventParams) => {
        const event = params.event as ResearchEvent;
        recordEvent({ sequence: event.meta.sequence, type: event.type });
        const collector = collectorRef.current;
        if (!collector || params.client_run_id !== collector.clientRunId) return;
        pushItems(collector.onEvent(event, params.display ?? null));
      });
      client.on('run.finished', (params: RunFinishedParams) => {
        const collector = collectorRef.current;
        if (!collector || params.client_run_id !== collector.clientRunId) return;
        pushItems(collector.onFinished(params));
        endRun(collector);
      });
    },
    onCrash: (report: CrashReport) => {
      const exitText = report.exit.code !== null ? `exit ${report.exit.code}` : `signal ${report.exit.signal ?? '?'}`;
      clientRef.current = null;
      const collector = collectorRef.current;
      if (collector) {
        pushItems(collector.abort('failed', 'The backend stopped during the run.'));
        endRun(collector);
      }
      const id = `bridge:crash:${Date.now()}`;
      pushItems([
        { kind: 'notice', id, runId: id, tone: 'loss', text: `Bridge stopped (${exitText}). The next message restarts it.` },
        ...(report.stderrTail.length > 0
          ? [{ kind: 'command-output' as const, id: `${id}:stderr`, lines: report.stderrTail }]
          : []),
      ]);
    },
  });
  bridgeRef.current = bridge;

  // Forward every bridge request through the live client; `session.*` results
  // update the session the header and /debug report.
  const bridgeProxy = {
    closed: false,
    async request(method: MethodName, params: unknown, options?: RequestOptions): Promise<unknown> {
      const client = await bridge.ensure();
      const result = await client.request(method, params as never, options);
      if (method === 'session.new' || method === 'session.resume') {
        const session = (result as { session?: SessionInfo }).session;
        if (session) {
          sessionRef.current = { ...sessionRef.current, id: session.id, title: session.title };
          setSessionTitle(session.title);
        }
        lastRunRef.current = null;
        lastTrailRef.current = null;
      }
      return result;
    },
    on: () => () => undefined,
    close: () => undefined,
  } as unknown as Bridge;

  const snapshotOf = (): AppSnapshot => {
    const info = sessionRef.current;
    const current = storeRef.current.getState();
    return {
      running: runningRef.current,
      phase: current.phase as Phase,
      latestSequence: current.latestSequence,
      sessionId: info.id,
      sessionTitle: info.title,
      mode: modeRef.current,
      model: info.model,
      dataDir: info.dataDir,
      protocolVersion: PROTOCOL_VERSION,
      bridgePid: bridgeRef.current?.pid ?? null,
      recentEvents: recentRef.current,
      stderrTail: bridgeRef.current?.stderrTail(STDERR_LINES) ?? [],
    };
  };

  const startRun = (query: string): void => {
    const clientRunId = newRunId();
    const store = createPresentationStore();
    const collector = new RunCollector({ clientRunId, query, store });
    collectorRef.current = collector;
    storeRef.current = store;
    runningRef.current = true;
    setRunStore(store);
    setRunning(true);
    setRunStartedAt(collector.startedAt);
    pushItems([userItem(clientRunId, query)]);
    const request: RunStartParams = { client_run_id: clientRunId, mode: modeRef.current, query };
    void (async () => {
      try {
        const client = await bridge.ensure();
        await client.request('run.start', request);
      } catch (error) {
        pushItems(collector.abort('failed', errorMessage(error)));
        endRun(collector);
      }
    })();
  };

  const commandCtx: CommandContext = {
    bridge: bridgeProxy,
    getState: snapshotOf,
    getLastRun: () => lastRunRef.current,
    print: (item) => pushItems([item]),
    clearTranscript: () => {
      setCommitted([]);
      setEpoch((value) => value + 1);
    },
    openPicker: (sessions) => setPicker(sessions),
    setMode: (next) => {
      modeRef.current = next;
      setModeState(next);
    },
    exit: () => exit(),
    retry: () => {
      const query = lastRunRef.current?.query;
      if (query) submit(query);
    },
  };

  const submit = (text: string): void => {
    const trimmed = text.trim();
    if (trimmed === '') return;
    const parsed = parseCommand(trimmed);
    if (parsed !== null) {
      if (parsed.name === 'help') {
        setHelpOpen(true);
        return;
      }
      void runCommand(parsed, commandCtx);
      return;
    }
    if (runningRef.current) {
      queueRef.current.push(trimmed);
      setQueuedCount(queueRef.current.length);
      return;
    }
    startRun(trimmed);
  };

  const cancelRun = (): void => {
    const collector = collectorRef.current;
    if (!collector) return;
    collector.store.dispatch({ type: 'local-phase', phase: 'cancelling' });
    void (async () => {
      try {
        const client = await bridge.ensure();
        await client.request('run.cancel', { client_run_id: collector.clientRunId });
      } catch (error) {
        pushItems([
          { kind: 'notice', id: `cancel:${Date.now()}`, runId: collector.clientRunId, tone: 'warn', text: errorMessage(error) },
        ]);
      }
    })();
  };

  const clearScreen = (): void => {
    stdout?.write('\x1b[2J\x1b[3J\x1b[H');
    setEpoch((value) => value + 1);
  };

  const onAction = (action: Action): void => {
    switch (action.type) {
      case 'cancelRun':
        cancelRun();
        return;
      case 'toggleDetails': {
        if (runningRef.current) {
          setDetailsOpen((open) => !open);
          return;
        }
        const trail = lastTrailRef.current;
        if (trail === null || trail.toolCount <= 0) {
          flashNotice('No earlier run to expand');
          return;
        }
        const id = `${trail.runId}:trail:${Date.now()}`;
        pushItems([
          {
            kind: 'activity-trail',
            id,
            runId: trail.runId,
            collapsed: false,
            toolCount: trail.toolCount,
            failedNouns: trail.failedNouns,
            rows: trail.rows,
          },
        ]);
        return;
      }
      case 'clearScreen':
        clearScreen();
        return;
      case 'armExit':
        flashNotice('Press Ctrl+C again to exit');
        return;
      case 'exit':
        exit();
        return;
      default:
        return;
    }
  };

  const resumeFrom = (id: string): void => {
    setPicker(null);
    void runCommand({ name: 'resume', args: [id], raw: `/resume ${id}` }, commandCtx);
  };

  useInput(
    (_input, key) => {
      if (key.escape || key.return) setHelpOpen(false);
    },
    { isActive: helpOpen },
  );

  const collector = collectorRef.current;
  const liveText = running && collector ? collector.liveText(state.responseText) : '';
  const liveRows = Math.max(4, (stdout?.rows ?? 30) - 12);
  const live = running && collector
    ? collector.liveActivities(state)
    : { operation: state.currentOperation, activities: state.activities };

  return (
    <Box flexDirection="column" width={width}>
      <Static key={epoch} items={committed}>
        {(item) => (
          <Box key={item.id} flexDirection="column" width={width}>
            <TranscriptItemView item={item} width={width} />
          </Box>
        )}
      </Static>

      {running ? (
        <LiveActivity
          frame={elapsed.frame % SPINNER_FRAMES.length}
          operation={live.operation}
          elapsedSeconds={elapsed.seconds}
          activeTools={state.activeTools}
          activities={live.activities}
          width={width}
        />
      ) : null}
      {running && detailsOpen ? (
        <ActivityTrail
          expanded
          failedNouns={collector?.failedNouns ?? []}
          activities={live.activities}
          width={width}
        />
      ) : null}
      {running && liveText.trim() !== '' ? (
        <ClippedTail maxRows={liveRows}>
          <StreamingAnswer text={liveText} width={width} showBullet />
        </ClippedTail>
      ) : null}
      {queuedCount > 0 ? <Text color={color('dim')}>{`queued ${queuedCount}`}</Text> : null}
      {notice !== null ? <Text color={color('dim')}>{notice}</Text> : null}

      {picker !== null ? (
        <SessionPicker sessions={picker} onSelect={resumeFrom} onClose={() => setPicker(null)} />
      ) : null}
      {helpOpen ? <HelpPanel /> : null}

      <Composer
        mode={running ? 'running' : 'idle'}
        history={[]}
        onSubmit={(text) => submit(text)}
        onAction={onAction}
        isActive={picker === null && !helpOpen}
      />
      <StatusLine title={sessionTitle} mode={mode} running={running} hint={modelId} />
    </Box>
  );
}
