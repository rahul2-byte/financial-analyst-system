/**
 * In-memory `Bridge` for unit tests and screenshots.
 *
 * It implements the same interface as `BridgeClient`, records every call and
 * replays scripted runs. Scripted `run.event` notifications are delivered
 * synchronously inside `run.start`, so a test can `await run.start(...)` and
 * then assert on the resulting state without timers.
 */
import type { Display, ResearchEvent, RunFinishedParams, SessionInfo } from '../protocol/generated.js';
import type {
  Bridge,
  MethodName,
  NotificationHandler,
  NotificationName,
  NotificationParams,
  ParamsOf,
  ResultOf,
} from '../protocol/methods.js';
import { PROTOCOL_VERSION } from '../protocol/version.js';
import { BridgeError, INTERNAL_ERROR } from './client.js';

export type RunOutcome = RunFinishedParams['outcome'];

export interface ScriptedEvent {
  event: ResearchEvent;
  display?: Display | null;
}

export interface ScriptedRun {
  clientRunId: string;
  events?: ScriptedEvent[];
  outcome?: RunOutcome;
  runId?: string | null;
  artifactPath?: string | null;
  message?: string | null;
  report?: RunFinishedParams['report'];
  evidenceStatus?: RunFinishedParams['evidence_status'];
  evidenceAvailability?: RunFinishedParams['evidence_availability'];
}

export interface RecordedCall {
  method: MethodName;
  params: unknown;
}

export const FAKE_SESSION: SessionInfo = {
  id: 'fake-session',
  title: 'Fake research session',
  message_count: 0,
  run_count: 0,
};

function defaultResult(method: MethodName): unknown {
  switch (method) {
    case 'initialize':
      return {
        protocol_version: PROTOCOL_VERSION,
        server_version: 'fake',
        session: { ...FAKE_SESSION },
        mode: 'guided',
        data_dir: '.finai',
        model: null,
      };
    case 'run.start':
      return { accepted: true };
    case 'run.cancel':
      return { cancelled: false };
    case 'session.new':
    case 'session.resume':
      return { session: { ...FAKE_SESSION } };
    case 'session.list':
      return { sessions: [] };
    case 'session.history':
      return { queries: [] };
    case 'context.info':
    case 'context.compact':
      return {};
    case 'trace.tail':
      return { records: [], ledger_path: '' };
    case 'shutdown':
      return {};
  }
}

export class FakeBridge implements Bridge {
  readonly calls: RecordedCall[] = [];
  readonly scriptedRuns: ScriptedRun[] = [];
  readonly sentNotifications: Array<{ method: string; params: unknown }> = [];

  readonly #handlers = new Map<string, Set<(params: unknown) => void>>();
  readonly #results = new Map<string, unknown>();
  readonly #errors = new Map<string, BridgeError>();
  #closed = false;
  #currentRunId: string | null = null;

  get closed(): boolean {
    return this.#closed;
  }

  /** The accepted run that has not been cancelled/finished yet, if any. */
  get currentRunId(): string | null {
    return this.#currentRunId;
  }

  /** Queue a run to be replayed on the next matching `run.start`. */
  scriptRun(run: ScriptedRun): this {
    this.scriptedRuns.push(run);
    return this;
  }

  /** Override the result of a method. */
  setResult<M extends MethodName>(method: M, result: ResultOf<M>): this {
    this.#results.set(method, result);
    return this;
  }

  /** Make every call to a method fail with a JSON-RPC error. */
  setError(method: MethodName, error: { code: number; message: string; data?: unknown }): this {
    this.#errors.set(method, new BridgeError(error.code, error.message, error.data));
    return this;
  }

  clearError(method: MethodName): this {
    this.#errors.delete(method);
    return this;
  }

  /** Emit a notification to registered handlers (stepwise streaming in tests). */
  emitNotification<N extends NotificationName>(method: N, params: NotificationParams<N>): void {
    this.sentNotifications.push({ method, params });
    const handlers = this.#handlers.get(method);
    if (handlers === undefined) return;
    for (const handler of [...handlers]) handler(params);
  }

  request<M extends MethodName>(method: M, params: ParamsOf<M>): Promise<ResultOf<M>> {
    if (this.#closed) {
      return Promise.reject(new BridgeError(INTERNAL_ERROR, 'fake bridge is closed'));
    }

    this.calls.push({ method, params });

    const error = this.#errors.get(method);
    if (error !== undefined) return Promise.reject(error);

    if (method === 'run.start') {
      this.#replayRun(params as ParamsOf<'run.start'>);
    } else if (method === 'run.cancel') {
      const clientRunId = (params as ParamsOf<'run.cancel'>).client_run_id;
      const cancelled = this.#currentRunId === clientRunId;
      if (cancelled) this.#currentRunId = null;
      this.#results.set('run.cancel', { cancelled });
    } else if (method === 'shutdown') {
      this.#closed = true;
    }

    const result = this.#results.has(method) ? this.#results.get(method) : defaultResult(method);
    // Deep-clone so callers cannot mutate the fake's stored state.
    return Promise.resolve(structuredClone(result) as ResultOf<M>);
  }

  on<N extends NotificationName>(method: N, handler: NotificationHandler<N>): () => void {
    let handlers = this.#handlers.get(method);
    if (handlers === undefined) {
      handlers = new Set();
      this.#handlers.set(method, handlers);
    }
    const wrapped = handler as (params: unknown) => void;
    handlers.add(wrapped);
    return () => {
      const current = this.#handlers.get(method);
      if (current === undefined) return;
      current.delete(wrapped);
      if (current.size === 0) this.#handlers.delete(method);
    };
  }

  close(): void {
    this.#closed = true;
    this.#handlers.clear();
    this.#currentRunId = null;
  }

  #replayRun(params: ParamsOf<'run.start'>): void {
    const index = this.scriptedRuns.findIndex((run) => run.clientRunId === params.client_run_id);
    const run = index === -1 ? undefined : this.scriptedRuns.splice(index, 1)[0];
    this.#currentRunId = params.client_run_id;
    if (run === undefined) return;

    for (const item of run.events ?? []) {
      this.emitNotification('run.event', {
        client_run_id: params.client_run_id,
        event: item.event,
        display: item.display ?? null,
      });
    }

    const finalEvent = run.events?.at(-1)?.event;
    const finished: RunFinishedParams = {
      client_run_id: params.client_run_id,
      outcome: run.outcome ?? 'completed',
      run_id: run.runId ?? finalEvent?.meta.run_id ?? null,
      artifact_path: run.artifactPath ?? null,
      message: run.message ?? null,
      report: run.report ?? null,
      evidence_status: run.evidenceStatus ?? null,
      evidence_availability: run.evidenceAvailability ?? null,
    };
    this.emitNotification('run.finished', finished);
    this.#currentRunId = null;
  }
}
