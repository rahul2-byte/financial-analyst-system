/**
 * NDJSON framing for the bridge wire protocol.
 *
 * One JSON object per line, UTF-8, terminated by `\n`. Lines longer than
 * `MAX_LINE_BYTES` are dropped as a whole and reported once through `onError`
 * (mapped to a JSON-RPC `-32700` parse error by the caller).
 */
import type { Readable, Writable } from 'node:stream';

/** Hard line limit: 8 MiB, matching the Python `NdjsonReader`. */
export const MAX_LINE_BYTES = 8 * 1024 * 1024;

const NEWLINE = 0x0a;
const CARRIAGE_RETURN = 0x0d;

/** Framing failure; `code` matches the JSON-RPC parse error code. */
export class FramingError extends Error {
  readonly code = -32700;

  constructor(message: string) {
    super(message);
    this.name = 'FramingError';
  }
}

export interface LineReaderOptions {
  /** Called once per complete, non-empty line. */
  onLine: (line: string) => void;
  /** Called when a line is dropped (oversize), with a `FramingError`. */
  onError?: (error: FramingError) => void;
  /** Defaults to {@link MAX_LINE_BYTES}. */
  maxLineBytes?: number;
}

/**
 * Incremental UTF-8 NDJSON line splitter.
 *
 * Byte chunks are buffered until a newline arrives, so a multi-byte character
 * split across two chunks is decoded correctly (decoding never happens on a
 * partial sequence).
 */
export class LineReader {
  readonly #onLine: (line: string) => void;
  readonly #onError: ((error: FramingError) => void) | undefined;
  readonly #maxLineBytes: number;

  #chunks: Buffer[] = [];
  #bytes = 0;
  #dropping = false;

  constructor(options: LineReaderOptions) {
    this.#onLine = options.onLine;
    this.#onError = options.onError;
    this.#maxLineBytes = options.maxLineBytes ?? MAX_LINE_BYTES;
  }

  /** Bytes buffered for the current (unterminated) line. */
  get bufferedBytes(): number {
    return this.#bytes;
  }

  /** True while discarding the remainder of an oversize line. */
  get dropping(): boolean {
    return this.#dropping;
  }

  push(chunk: Buffer | Uint8Array | string): void {
    const buffer = typeof chunk === 'string' ? Buffer.from(chunk, 'utf8') : Buffer.from(chunk);
    let start = 0;

    for (;;) {
      const newlineAt = buffer.indexOf(NEWLINE, start);
      if (newlineAt === -1) {
        this.#append(buffer.subarray(start));
        return;
      }

      const part = buffer.subarray(start, newlineAt);
      start = newlineAt + 1;

      if (this.#dropping) {
        // The rest of this oversize line is discarded up to its newline.
        this.#dropping = false;
        continue;
      }

      if (this.#bytes + part.length > this.#maxLineBytes) {
        this.#resetPending();
        this.#reportOversize();
        continue;
      }

      const lineBytes = this.#bytes === 0 ? Buffer.from(part) : Buffer.concat([...this.#chunks, part]);
      this.#resetPending();
      this.#emit(lineBytes);
    }
  }

  /** Drop any partial line (used on close). */
  reset(): void {
    this.#resetPending();
    this.#dropping = false;
  }

  #append(part: Buffer): void {
    if (this.#dropping || part.length === 0) return;
    if (this.#bytes + part.length > this.#maxLineBytes) {
      this.#resetPending();
      this.#dropping = true;
      this.#reportOversize();
      return;
    }
    this.#chunks.push(Buffer.from(part));
    this.#bytes += part.length;
  }

  #emit(lineBytes: Buffer): void {
    let end = lineBytes.length;
    if (end > 0 && lineBytes[end - 1] === CARRIAGE_RETURN) end -= 1;
    if (end === 0) return; // tolerate blank keep-alive lines
    this.#onLine(lineBytes.toString('utf8', 0, end));
  }

  #reportOversize(): void {
    this.#onError?.(
      new FramingError(`line exceeded ${this.#maxLineBytes} bytes and was dropped`),
    );
  }

  #resetPending(): void {
    this.#chunks = [];
    this.#bytes = 0;
  }
}

/**
 * Wire a {@link LineReader} to a readable stream.
 * Returns a detach function; the caller must call it on close.
 */
export function attachLineReader(readable: Readable, options: LineReaderOptions): () => void {
  const reader = new LineReader(options);
  const onData = (chunk: Buffer | string) => {
    reader.push(chunk);
  };
  const onEnd = () => {
    reader.reset();
  };
  readable.on('data', onData);
  readable.on('end', onEnd);
  return () => {
    readable.off('data', onData);
    readable.off('end', onEnd);
    reader.reset();
  };
}

/**
 * Serialize one JSON-RPC message as a single NDJSON line and wait until the
 * stream has accepted it (write callback), so backpressure is respected.
 */
export function writeMessage(stream: Writable, message: unknown): Promise<void> {
  const encoded = JSON.stringify(message);
  if (typeof encoded !== 'string') {
    return Promise.reject(new FramingError('message is not JSON-serializable'));
  }

  if (stream.destroyed || stream.writableEnded) {
    return Promise.reject(new FramingError('cannot write to a closed stream'));
  }

  const payload = Buffer.from(`${encoded}\n`, 'utf8');

  return new Promise<void>((resolve, reject) => {
    let settled = false;
    const finish = (error?: Error | null): void => {
      if (settled) return;
      settled = true;
      stream.off('error', onError);
      if (error) reject(error);
      else resolve();
    };
    const onError = (error: Error): void => {
      finish(error);
    };

    stream.once('error', onError);
    stream.write(payload, (error?: Error | null) => {
      finish(error ?? null);
    });
  });
}
