/**
 * Typed JSON-RPC method/notification surface.
 *
 * Field shapes come exclusively from `generated.ts`; this module only maps
 * method names to the generated params/result types.
 */
import type {
  BridgeLogParams,
  ContextCompactParams,
  ContextCompactResult,
  ContextInfoParams,
  ContextInfoResult,
  InitializeParams,
  InitializeResult,
  RunCancelParams,
  RunCancelResult,
  RunEventParams,
  RunFinishedParams,
  RunStartParams,
  RunStartResult,
  SessionHistoryParams,
  SessionHistoryResult,
  SessionListParams,
  SessionListResult,
  SessionNewParams,
  SessionNewResult,
  SessionResumeParams,
  SessionResumeResult,
  ShutdownParams,
  ShutdownResult,
  TraceTailParams,
  TraceTailResult,
} from './generated.js';

export interface MethodMap {
  initialize: { params: InitializeParams; result: InitializeResult };
  'run.start': { params: RunStartParams; result: RunStartResult };
  'run.cancel': { params: RunCancelParams; result: RunCancelResult };
  'session.new': { params: SessionNewParams; result: SessionNewResult };
  'session.resume': { params: SessionResumeParams; result: SessionResumeResult };
  'session.list': { params: SessionListParams; result: SessionListResult };
  'session.history': { params: SessionHistoryParams; result: SessionHistoryResult };
  'context.info': { params: ContextInfoParams; result: ContextInfoResult };
  'context.compact': { params: ContextCompactParams; result: ContextCompactResult };
  'trace.tail': { params: TraceTailParams; result: TraceTailResult };
  shutdown: { params: ShutdownParams; result: ShutdownResult };
}

export type MethodName = keyof MethodMap;
export type ParamsOf<M extends MethodName> = MethodMap[M]['params'];
export type ResultOf<M extends MethodName> = MethodMap[M]['result'];

/** Notifications sent by the Python bridge (no `id`, no response). */
export interface NotificationMap {
  'run.event': RunEventParams;
  'run.finished': RunFinishedParams;
  'bridge.log': BridgeLogParams;
}

export type NotificationName = keyof NotificationMap;
export type NotificationParams<N extends NotificationName> = NotificationMap[N];

export type NotificationHandler<N extends NotificationName> = (
  params: NotificationParams<N>,
) => void;

export interface RequestOptions {
  /** Overrides the per-method default (see `DEFAULT_TIMEOUTS`). */
  timeoutMs?: number;
  /** Abort the pending request; rejects with an `AbortError`-like `BridgeError`. */
  signal?: AbortSignal;
}

/**
 * Shared shape of `BridgeClient` and `FakeBridge`, so UI code can be tested
 * against either without a real process.
 */
export interface Bridge {
  readonly closed: boolean;
  request<M extends MethodName>(
    method: M,
    params: ParamsOf<M>,
    options?: RequestOptions,
  ): Promise<ResultOf<M>>;
  on<N extends NotificationName>(method: N, handler: NotificationHandler<N>): () => void;
  close(reason?: string): void;
}
