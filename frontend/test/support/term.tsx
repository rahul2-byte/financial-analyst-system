/**
 * Terminal harness shared by the screenshot script (scripts/snapshot.tsx) and the
 * app regression tests. Ink writes into an `@xterm/headless` buffer, so a test can
 * check what a user would see (screen plus scrollback), not only Ink's last frame.
 */
import { readFileSync } from 'node:fs';
import { EventEmitter } from 'node:events';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ReactElement } from 'react';
import { render } from 'ink';
import xtermHeadless from '@xterm/headless';

import { FakeBridge } from '../../src/bridge/fake.js';
import type { MethodName, ParamsOf, ResultOf } from '../../src/protocol/methods.js';
import type { RunStartParams } from '../../src/protocol/generated.js';

const { Terminal } = xtermHeadless;
type TerminalInstance = InstanceType<typeof Terminal>;

const GOLDENS = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'goldens');

/** The model the replay bridge reports in `initialize`, so the header shows it. */
export const REPLAY_MODEL_ID = 'claude-haiku-5.5';

export interface GoldenEvent {
  event: { type: string; message?: string; meta: { sequence: number } };
  display?: unknown;
}

export interface Replay {
  /** File name under test/goldens. */
  readonly golden: string;
  /** Emit only the first `limit` events. */
  readonly limit?: number;
  /** Send `run.finished` after the events; false leaves the run open. */
  readonly finish: boolean;
  /** Pause between events, as the Python fake bridge does. Default: emit at once. */
  readonly delayMs?: number;
}

/** Ink's stdout: a columns/rows tty whose writes land in an xterm buffer. */
export class TermStdout extends EventEmitter {
  readonly isTTY = true;
  readonly columns: number;
  readonly rows: number;
  /** Every chunk Ink wrote, in order (after tty translation). */
  readonly raw: string[] = [];
  readonly #term: TerminalInstance;

  constructor(term: TerminalInstance, columns: number, rows: number) {
    super();
    this.#term = term;
    this.columns = columns;
    this.rows = rows;
  }

  /**
   * A real tty turns every LF into CRLF (the ONLCR line discipline). xterm does not,
   * so without this a bare LF keeps the cursor column and Ink's output staircases.
   */
  write(data: string): boolean {
    const tty = data.replace(/\r?\n/g, '\r\n');
    this.raw.push(tty);
    this.#term.write(tty);
    return true;
  }
}

/** Ink's stdin: keystrokes are pushed as `data` chunks. */
export class FakeStdin extends EventEmitter {
  readonly isTTY = true;
  #buffer: string[] = [];
  setRawMode(): this {
    return this;
  }
  setEncoding(): this {
    return this;
  }
  resume(): this {
    return this;
  }
  pause(): this {
    return this;
  }
  ref(): this {
    return this;
  }
  unref(): this {
    return this;
  }
  /** Ink 6 reads via the `readable` event and `read()`, so keystrokes are buffered here. */
  read(): string | null {
    return this.#buffer.shift() ?? null;
  }
  send(chunk: string): void {
    this.#buffer.push(chunk);
    this.emit('readable');
  }
}

/** Replays golden events for `run.start`, as the Python bridge would stream them. */
export class ReplayBridge extends FakeBridge {
  readonly #replay: Replay | undefined;
  readonly #golden: GoldenEvent[] = [];
  /** `finished` block of a report fixture (`goldens/reports/*.json`), merged into `run.finished`. */
  #finished: Record<string, unknown> = {};
  readonly #timers = new Set<ReturnType<typeof setTimeout>>();

  /** `goldensDir` is needed when this module is bundled; `import.meta.url` then points elsewhere. */
  constructor(replay: Replay | undefined, goldensDir: string = GOLDENS) {
    super();
    this.#replay = replay;
    if (replay) {
      const data = JSON.parse(readFileSync(path.join(goldensDir, replay.golden), 'utf8')) as {
        events: GoldenEvent[];
        finished?: Record<string, unknown>;
      };
      this.#golden = data.events;
      this.#finished = data.finished ?? {};
    }
  }

  override async request<M extends MethodName>(method: M, params: ParamsOf<M>): Promise<ResultOf<M>> {
    if (method === 'initialize') {
      const result = await super.request(method, params);
      return { ...result, model: { id: REPLAY_MODEL_ID } } as ResultOf<M>;
    }
    if (method !== 'run.start' || this.#replay === undefined) {
      return super.request(method, params);
    }
    const replay = this.#replay;
    const clientRunId = (params as unknown as RunStartParams).client_run_id;
    const count = replay.limit ?? this.#golden.length;
    const steps: Array<() => void> = this.#golden.slice(0, count).map((item) => () => {
      this.emitNotification('run.event', {
        client_run_id: clientRunId,
        display: (item.display ?? null) as never,
        event: item.event as never,
      });
    });
    if (replay.finish) {
      const last = this.#golden[this.#golden.length - 1]?.event;
      const derived = last?.type === 'run.failed' ? 'failed' : last?.type === 'run.cancelled' ? 'cancelled' : 'completed';
      const outcome = (this.#finished.outcome as string | undefined) ?? derived;
      steps.push(() =>
        this.emitNotification('run.finished', {
          client_run_id: clientRunId,
          artifact_path: null as never,
          message: (last?.message ?? '') as never,
          run_id: '' as never,
          ...(this.#finished as object),
          outcome: outcome as never,
        }),
      );
    }
    if (!replay.delayMs) {
      steps.forEach((step) => step());
    } else {
      steps.forEach((step, index) => {
        const timer = setTimeout(() => {
          this.#timers.delete(timer);
          step();
        }, index * replay.delayMs!);
        this.#timers.add(timer);
      });
    }
    return Promise.resolve({ accepted: true } as ResultOf<M>);
  }

  override close(): void {
    for (const timer of this.#timers) clearTimeout(timer);
    this.#timers.clear();
    super.close();
  }
}

export const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** Resolves once xterm has parsed everything written so far. */
export function flush(term: TerminalInstance): Promise<void> {
  return new Promise((resolve) => term.write('', resolve));
}

/** Every line in the buffer, scrollback first, then the visible screen. */
export function terminalLines(term: TerminalInstance): string[] {
  const buffer = term.buffer.active;
  const lines: string[] = [];
  for (let index = 0; index < buffer.length; index += 1) {
    lines.push(buffer.getLine(index)?.translateToString(true) ?? '');
  }
  return lines;
}

export interface Mounted {
  readonly term: TerminalInstance;
  readonly stdin: FakeStdin;
  readonly stdout: TermStdout;
  readonly instance: ReturnType<typeof render>;
}

/** Renders `element` into a fresh xterm of the given size, with keystrokes via `stdin.send`. */
export function mount(element: ReactElement, cols: number, rows: number): Mounted {
  const term = new Terminal({ cols, rows, allowProposedApi: true, scrollback: 500 });
  const stdout = new TermStdout(term, cols, rows);
  const stdin = new FakeStdin();
  const instance = render(element, {
    stdout: stdout as unknown as NodeJS.WriteStream,
    stdin: stdin as unknown as NodeJS.ReadStream,
    exitOnCtrlC: false,
    patchConsole: false,
  });
  return { term, stdin, stdout, instance };
}
