/**
 * JSON-RPC 2.0 client over the bridge's NDJSON stdio pair.
 *
 * Requests carry integer ids starting at 1. Every request has exactly one
 * response; notifications (no `id`) are fanned out to registered handlers.
 */
import type { Readable, Writable } from 'node:stream';

import { attachLineReader, FramingError, writeMessage } from './framing.js';
import type {
  Bridge,
  MethodName,
  NotificationHandler,
  NotificationName,
  ParamsOf,
  RequestOptions,
  ResultOf,
} from '../protocol/methods.js';

/** Default request timeout. */
export const DEFAULT_TIMEOUT_MS = 10_000;
/** `initialize` has to wait for the Python runtime to import. */
export const INITIALIZE_TIMEOUT_MS = 30_000;
/** `run.start` only accepts the run; events stream afterwards. */
export const RUN_START_TIMEOUT_MS = 5_000;
/** JSON-RPC internal error. Used for transport/close failures, not RPC errors. */
export const INTERNAL_ERROR = -32603;

export const DEFAULT_TIMEOUTS: Readonly<Record<string, number>> = Object.freeze({
  initialize: INITIALIZE_TIMEOUT_MS,
  'run.start': RUN_START_TIMEOUT_MS,
});

/** A JSON-RPC error response, mapped to a throwable. */
export class BridgeError extends Error {
  readonly code: number;
  readonly data: unknown;

  constructor(code: number, message: string, data?: unknown) {
    super(message);
    this.name = 'BridgeError';
    this.code = code;
    this.data = data;
  }

  static fromErrorObject(error: unknown): BridgeError {
    const object = typeof error === 'object' && error !== null ? (error as Record<string, unknown>) : {};
    const code = typeof object.code === 'number' ? object.code : INTERNAL_ERROR;
    const message = typeof object.message === 'string' ? object.message : 'unknown bridge error';
    return new BridgeError(code, message, object.data);
  }
}

/** A request that did not receive a response in time. */
export class BridgeTimeoutError extends Error {
  readonly method: MethodName;
  readonly timeoutMs: number;

  constructor(method: MethodName, timeoutMs: number) {
    super(`bridge request "${method}" timed out after ${timeoutMs} ms`);
    this.name = 'BridgeTimeoutError';
    this.method = method;
    this.timeoutMs = timeoutMs;
  }
}

export interface BridgeClientOptions {
  readable: Readable;
  writable: Writable;
  /** Per-method overrides; `default` applies to unlisted methods. */
  timeouts?: Partial<Record<MethodName | 'default', number>>;
  /** Malformed frames, unknown ids and unserializable payloads land here. */
  onProtocolError?: (error: Error) => void;
  /** Unknown notification methods are tolerated (forward compatibility). */
  onUnknownNotification?: (method: string, params: unknown) => void;
  /** Ids start here (tests use it to pin the wire format). */
  firstRequestId?: number;
}

interface PendingRequest {
  method: MethodName;
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
  cleanup: () => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export class BridgeClient implements Bridge {
  readonly #writable: Writable;
  readonly #timeouts: Partial<Record<MethodName | 'default', number>>;
  readonly #onProtocolError: ((error: Error) => void) | undefined;
  readonly #onUnknownNotification: ((method: string, params: unknown) => void) | undefined;

  readonly #pending = new Map<number, PendingRequest>();
  readonly #handlers = new Map<string, Set<(params: unknown) => void>>();

  #nextId: number;
  #closed = false;
  #detachReader: (() => void) | undefined;
  #detachClose: (() => void) | undefined;

  constructor(options: BridgeClientOptions) {
    this.#writable = options.writable;
    this.#timeouts = options.timeouts ?? {};
    this.#onProtocolError = options.onProtocolError;
    this.#onUnknownNotification = options.onUnknownNotification;
    this.#nextId = options.firstRequestId ?? 1;

    this.#detachReader = attachLineReader(options.readable, {
      onLine: (line) => {
        this.#handleLine(line);
      },
      onError: (error) => {
        this.#onProtocolError?.(error);
      },
    });

    // A dead transport must not leave requests hanging until their timeout.
    const onGone = () => {
      this.#failAll(new BridgeError(INTERNAL_ERROR, 'bridge stream closed'));
    };
    options.readable.once('close', onGone);
    options.readable.once('end', onGone);
    this.#detachClose = () => {
      options.readable.off('close', onGone);
      options.readable.off('end', onGone);
    };
  }

  get closed(): boolean {
    return this.#closed;
  }

  /** Number of requests still awaiting a response (diagnostics/tests). */
  get pendingCount(): number {
    return this.#pending.size;
  }

  request<M extends MethodName>(
    method: M,
    params: ParamsOf<M>,
    options: RequestOptions = {},
  ): Promise<ResultOf<M>> {
    if (this.#closed) {
      return Promise.reject(new BridgeError(INTERNAL_ERROR, `bridge client is closed`));
    }

    const id = this.#nextId;
    this.#nextId += 1;
    const timeoutMs = options.timeoutMs ?? this.#timeouts[method] ?? this.#timeouts.default ?? DEFAULT_TIMEOUT_MS;

    return new Promise<ResultOf<M>>((resolve, reject) => {
      const signal = options.signal;
      if (signal?.aborted) {
        reject(new BridgeError(INTERNAL_ERROR, `bridge request "${method}" was aborted`));
        return;
      }

      const settle = (): void => {
        clearTimeout(timer);
        this.#pending.delete(id);
        signal?.removeEventListener('abort', onAbort);
      };
      const timer = setTimeout(() => {
        settle();
        reject(new BridgeTimeoutError(method, timeoutMs));
      }, timeoutMs);
      const onAbort = (): void => {
        settle();
        reject(new BridgeError(INTERNAL_ERROR, `bridge request "${method}" was aborted`));
      };
      signal?.addEventListener('abort', onAbort, { once: true });

      this.#pending.set(id, {
        method,
        resolve: (result) => {
          settle();
          resolve(result as ResultOf<M>);
        },
        reject: (error) => {
          settle();
          reject(error);
        },
        timer,
        cleanup: settle,
      });

      const message = { jsonrpc: '2.0', id, method, params } as const;
      writeMessage(this.#writable, message).catch((error: unknown) => {
        const pending = this.#pending.get(id);
        if (pending === undefined) return;
        pending.reject(
          new BridgeError(
            INTERNAL_ERROR,
            `failed to write "${method}" request: ${error instanceof Error ? error.message : String(error)}`,
          ),
        );
      });
    });
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

  /**
   * Stop accepting requests and reject everything still pending. The transport
   * streams are owned by the caller (`process.ts`), not by this client.
   */
  close(reason = 'bridge client closed'): void {
    if (this.#closed) return;
    this.#closed = true;
    this.#detachReader?.();
    this.#detachReader = undefined;
    this.#detachClose?.();
    this.#detachClose = undefined;
    this.#handlers.clear();
    this.#failAll(new BridgeError(INTERNAL_ERROR, reason));
  }

  #failAll(error: Error): void {
    for (const pending of [...this.#pending.values()]) {
      pending.reject(error);
    }
    this.#pending.clear();
  }

  #handleLine(line: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      this.#onProtocolError?.(new FramingError(`invalid JSON frame: ${line.slice(0, 120)}`));
      return;
    }

    if (!isRecord(parsed)) {
      this.#onProtocolError?.(new FramingError('JSON-RPC frame must be an object'));
      return;
    }

    const id = parsed.id;
    if (typeof id === 'number') {
      this.#handleResponse(id, parsed);
      return;
    }

    const method = parsed.method;
    if (typeof method === 'string') {
      this.#handleNotification(method, parsed.params);
      return;
    }

    this.#onProtocolError?.(new FramingError('JSON-RPC frame has neither id nor method'));
  }

  #handleResponse(id: number, message: Record<string, unknown>): void {
    const pending = this.#pending.get(id);
    if (pending === undefined) {
      this.#onProtocolError?.(new Error(`response for unknown request id ${id}`));
      return;
    }
    if (message.error !== undefined && message.error !== null) {
      pending.reject(BridgeError.fromErrorObject(message.error));
      return;
    }
    pending.resolve(message.result ?? null);
  }

  #handleNotification(method: string, params: unknown): void {
    const handlers = this.#handlers.get(method);
    if (handlers === undefined || handlers.size === 0) {
      this.#onUnknownNotification?.(method, params);
      return;
    }
    for (const handler of [...handlers]) {
      try {
        handler(params);
      } catch (error) {
        this.#onProtocolError?.(
          error instanceof Error ? error : new Error(`notification handler for "${method}" threw`),
        );
      }
    }
  }
}
