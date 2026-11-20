/**
 * Locate Python, spawn `python -m finai.bridge`, keep stderr, shut it down
 *.
 *
 * The POSIX-only fallbacks are deliberate: this frontend targets macOS/Linux
 * terminals; on Windows the `uv run` path is the supported one.
 */
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { createWriteStream, existsSync, mkdirSync, type WriteStream } from 'node:fs';
import path from 'node:path';
import { createInterface, type Interface } from 'node:readline';

import { writeMessage } from './framing.js';

/** Lines kept in memory for `/debug`. */
export const STDERR_RING_SIZE = 500;
/** Grace period after `shutdown` before SIGTERM. */
export const SIGTERM_AFTER_MS = 2_000;
/** Grace period after SIGTERM before SIGKILL. */
export const SIGKILL_AFTER_MS = 2_000;

export interface PythonCommand {
  command: string;
  args: readonly string[];
}

export interface BridgeExit {
  code: number | null;
  signal: NodeJS.Signals | null;
}

export interface SpawnBridgeOptions {
  /** Directory containing `pyproject.toml` (from `findRepoRoot`). */
  repoRoot: string;
  /** Relative paths resolve against `cwd`, like the Python CLI. */
  dataDir?: string;
  session?: string;
  replaySnapshots?: string;
  fakeEvents?: string;
  fakeDelayMs?: number;
  cwd?: string;
  /** Bypasses `findPython` (tests inject the stub server). */
  python?: PythonCommand;
  /** Defaults to `['-m', 'finai.bridge']`; tests pass a stub script instead. */
  moduleArgs?: readonly string[];
  /** Extra environment, merged last. */
  env?: NodeJS.ProcessEnv;
  /** Ring buffer size for stderr lines. */
  stderrRingSize?: number;
  /** When false, stderr is not appended to `<dataDir>/logs/bridge.stderr.log`. */
  stderrLog?: boolean;
  sigtermAfterMs?: number;
  sigkillAfterMs?: number;
  /** Test seam; defaults to `node:child_process.spawn`. */
  spawnImpl?: typeof spawn;
}

export interface ShutdownOptions {
  requestId?: number;
  sigtermAfterMs?: number;
  sigkillAfterMs?: number;
}

/**
 * Walk up from `from` until a directory containing `pyproject.toml` is found.
 */
export function findRepoRoot(from: string): string {
  let current = path.resolve(from);
  for (;;) {
    if (existsSync(path.join(current, 'pyproject.toml'))) return current;
    const parent = path.dirname(current);
    if (parent === current) {
      throw new Error(`could not find pyproject.toml above ${path.resolve(from)}`);
    }
    current = parent;
  }
}

/**
 * Python discovery order: `$FINAI_PYTHON`, `<repo>/.venv/bin/python`,
 * then `uv run --project <repo> python`.
 */
export function findPython(repoRoot: string, env: NodeJS.ProcessEnv = process.env): PythonCommand {
  const override = env.FINAI_PYTHON?.trim();
  if (override) return { command: override, args: [] };

  const venvPython = path.join(repoRoot, '.venv', 'bin', 'python');
  if (existsSync(venvPython)) return { command: venvPython, args: [] };

  return { command: 'uv', args: ['run', '--project', repoRoot, 'python'] };
}

/** Build the argv for `python -m finai.bridge` from the CLI options. */
export function buildBridgeArgs(options: SpawnBridgeOptions): string[] {
  const args = [...(options.moduleArgs ?? ['-m', 'finai.bridge'])];
  if (options.dataDir !== undefined) args.push('--data-dir', options.dataDir);
  if (options.session !== undefined) args.push('--session', options.session);
  if (options.replaySnapshots !== undefined) args.push('--replay-snapshots', options.replaySnapshots);
  if (options.fakeEvents !== undefined) args.push('--fake-events', options.fakeEvents);
  if (options.fakeDelayMs !== undefined) args.push('--fake-delay-ms', String(options.fakeDelayMs));
  return args;
}

/** Build the child environment. */
export function buildBridgeEnv(options: SpawnBridgeOptions, base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  return {
    ...base,
    PYTHONPATH: path.join(options.repoRoot, 'backend'),
    PYTHONUNBUFFERED: '1',
    ...options.env,
  };
}

/**
 * A spawned Python bridge. Events:
 * - `exit`  `(code: number | null, signal: NodeJS.Signals | null)`
 * - `stderr` `(line: string)`
 * - `spawn-error` `(error: Error)`
 */
export class BridgeProcess extends EventEmitter {
  readonly child: ChildProcessWithoutNullStreams;
  readonly stderrLines: string[];
  readonly stderrLogPath: string | null;
  readonly exit: Promise<BridgeExit>;

  readonly #stderrRingSize: number;
  readonly #logStream: WriteStream | null;
  readonly #readline: Interface;
  readonly #sigtermAfterMs: number;
  readonly #sigkillAfterMs: number;
  readonly #exitHooks: Array<(exit: BridgeExit) => void> = [];

  #exitResult: BridgeExit | null = null;
  #shutdownPromise: Promise<BridgeExit> | null = null;
  #nextShutdownId = 1;
  #stderrLogBroken = false;

  constructor(options: SpawnBridgeOptions) {
    super();
    const cwd = options.cwd ?? process.cwd();
    const python = options.python ?? findPython(options.repoRoot, process.env);
    const spawnImpl = options.spawnImpl ?? spawn;
    const args = [...python.args, ...buildBridgeArgs(options)];

    this.#stderrRingSize = options.stderrRingSize ?? STDERR_RING_SIZE;
    this.#sigtermAfterMs = options.sigtermAfterMs ?? SIGTERM_AFTER_MS;
    this.#sigkillAfterMs = options.sigkillAfterMs ?? SIGKILL_AFTER_MS;
    this.stderrLines = [];

    const logPath =
      options.stderrLog === false || options.dataDir === undefined
        ? null
        : path.resolve(cwd, options.dataDir, 'logs', 'bridge.stderr.log');
    this.stderrLogPath = logPath;
    if (logPath !== null) {
      try {
        mkdirSync(path.dirname(logPath), { recursive: true });
        this.#logStream = createWriteStream(logPath, { flags: 'a' });
        this.#logStream.on('error', () => {
          this.#stderrLogBroken = true;
        });
      } catch {
        this.#logStream = null;
        this.#stderrLogBroken = true;
      }
    } else {
      this.#logStream = null;
    }

    this.child = spawnImpl(python.command, args, {
      cwd,
      env: buildBridgeEnv(options),
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    this.exit = new Promise<BridgeExit>((resolve) => {
      this.child.once('exit', (code, signal) => {
        const result: BridgeExit = { code, signal };
        this.#exitResult = result;
        this.#stderrLogBroken = true;
        this.#logStream?.end();
        resolve(result);
        this.emit('exit', code, signal);
        for (const hook of this.#exitHooks.splice(0)) hook(result);
      });
    });

    this.child.once('error', (error) => {
      this.emit('spawn-error', error);
    });

    this.#readline = createInterface({ input: this.child.stderr, crlfDelay: Infinity });
    this.#readline.on('line', (line) => {
      this.#recordStderr(line);
    });

    // stdin errors (EPIPE when the child is already gone) are not fatal here;
    // pending requests fail through the transport-close path in BridgeClient.
    this.child.stdin.on('error', () => undefined);
    this.child.stdout.on('error', () => undefined);
  }

  get pid(): number | undefined {
    return this.child.pid;
  }

  get running(): boolean {
    return this.#exitResult === null;
  }

  /** Last `count` stderr lines (default: the whole ring buffer). */
  stderrTail(count = this.#stderrRingSize): string[] {
    if (count >= this.stderrLines.length) return [...this.stderrLines];
    return this.stderrLines.slice(this.stderrLines.length - count);
  }

  /**
   * Send `shutdown`, then SIGTERM after `sigtermAfterMs` and SIGKILL after a
   * further `sigkillAfterMs` if the child is still alive.
   */
  shutdown(options: ShutdownOptions = {}): Promise<BridgeExit> {
    if (this.#exitResult !== null) return Promise.resolve(this.#exitResult);
    if (this.#shutdownPromise !== null) return this.#shutdownPromise;

    const requestId = options.requestId ?? this.#nextShutdownId;
    this.#nextShutdownId = requestId + 1;
    this.#shutdownPromise = (async (): Promise<BridgeExit> => {
      try {
        await writeMessage(this.child.stdin, {
          jsonrpc: '2.0',
          id: requestId,
          method: 'shutdown',
          params: {},
        });
      } catch {
        // The child may already be gone; escalation below is harmless.
      }

      const sigtermAfterMs = options.sigtermAfterMs ?? this.#sigtermAfterMs;
      const sigkillAfterMs = options.sigkillAfterMs ?? this.#sigkillAfterMs;

      const termTimer = setTimeout(() => {
        if (this.#exitResult === null) this.signal('SIGTERM');
      }, sigtermAfterMs);
      termTimer.unref?.();

      const killTimer = setTimeout(() => {
        if (this.#exitResult === null) this.signal('SIGKILL');
      }, sigtermAfterMs + sigkillAfterMs);
      killTimer.unref?.();

      try {
        return await this.exit;
      } finally {
        clearTimeout(termTimer);
        clearTimeout(killTimer);
      }
    })();

    return this.#shutdownPromise;
  }

  /** Send a signal to the child (no-op once it has exited). */
  signal(signal: NodeJS.Signals = 'SIGTERM'): void {
    if (this.#exitResult !== null) return;
    try {
      this.child.kill(signal);
    } catch {
      // Already reaped.
    }
  }

  #recordStderr(line: string): void {
    this.stderrLines.push(line);
    if (this.stderrLines.length > this.#stderrRingSize) {
      this.stderrLines.splice(0, this.stderrLines.length - this.#stderrRingSize);
    }
    if (this.#logStream !== null && !this.#stderrLogBroken) {
      this.#logStream.write(`${line}\n`);
    }
    this.emit('stderr', line);
  }
}

/** `findRepoRoot` + `findPython` + `BridgeProcess`, the common path. */
export function spawnBridge(options: SpawnBridgeOptions): BridgeProcess {
  return new BridgeProcess(options);
}
