/**
 * Bridge lifecycle for the app: spawn `python -m finai.bridge`, run the
 * `initialize` handshake with a protocol check, route unexpected exits as crashes,
 * respawn once on the next submit, and shut down on exit.
 *
 * `BridgeController` holds the lifecycle and is plain TypeScript, so it can be
 * reasoned about without React. `useBridge` only mirrors its status into state.
 */
import { useEffect, useRef, useState } from 'react';

import { BridgeClient, DEFAULT_TIMEOUT_MS, DEFAULT_TIMEOUTS } from '../../bridge/client.js';
import {
  findPython,
  spawnBridge,
  type BridgeExit,
  type BridgeProcess,
  type PythonCommand,
  type SpawnBridgeOptions,
} from '../../bridge/process.js';
import type { InitializeResult } from '../../protocol/generated.js';
import type { Bridge } from '../../protocol/methods.js';
import { PROTOCOL_MISMATCH_MESSAGE, PROTOCOL_VERSION } from '../../protocol/version.js';

export const CLIENT_NAME = 'finai-ts';
export const CLIENT_VERSION = '0.1.0';
/** Two unexpected exits inside this window stop automatic respawn. */
export const CRASH_WINDOW_MS = 10_000;
/** Stderr lines shown with a crash notice. */
export const CRASH_TAIL_LINES = 5;

export interface BridgeLaunch {
  /** Directory holding `pyproject.toml`. */
  readonly repoRoot: string;
  /** The user's cwd; `dataDir` resolves against it. */
  readonly cwd: string;
  readonly dataDir?: string;
  readonly session?: string;
  readonly fakeEvents?: string;
  readonly fakeDelayMs?: number;
  readonly mode?: string;
  readonly columns: number;
  readonly rows: number;
}

export interface CrashReport {
  readonly exit: BridgeExit;
  readonly stderrTail: readonly string[];
}

export type BridgeStatus = 'starting' | 'ready' | 'failed';

/** Set when the first connect fails; the CLI turns it into exit code 1. */
export const startFailure: { message: string | null } = { message: null };

const liveProcesses = new Set<BridgeProcess>();

/** `FINAI_BRIDGE_CMD` replaces the Python discovery, e.g. `node test/fixtures/stub-bridge.mjs`. */
export function bridgeCommandOverride(env: NodeJS.ProcessEnv = process.env): PythonCommand | null {
  const raw = env.FINAI_BRIDGE_CMD?.trim();
  if (!raw) return null;
  const [command, ...args] = raw.split(/\s+/);
  return command ? { command, args } : null;
}

/** Stop every bridge process this UI started. Called by the CLI after Ink unmounts. */
export async function shutdownAllBridges(): Promise<void> {
  await Promise.all([...liveProcesses].map((proc) => proc.shutdown()));
}

export function spawnOptions(launch: BridgeLaunch): SpawnBridgeOptions {
  const override = bridgeCommandOverride();
  return {
    repoRoot: launch.repoRoot,
    cwd: launch.cwd,
    dataDir: launch.dataDir ?? '.finai',
    session: launch.session,
    fakeEvents: launch.fakeEvents,
    fakeDelayMs: launch.fakeDelayMs,
    python: override ?? findPython(launch.repoRoot),
    moduleArgs: override ? [] : undefined,
  };
}

/** `initialize` with the protocol version check. */
export async function handshake(client: Bridge, launch: BridgeLaunch): Promise<InitializeResult> {
  const info = await client.request('initialize', {
    client: { name: CLIENT_NAME, version: CLIENT_VERSION },
    protocol_version: PROTOCOL_VERSION,
    terminal: { columns: launch.columns, rows: launch.rows },
  });
  if (info.protocol_version !== PROTOCOL_VERSION) throw new Error(PROTOCOL_MISMATCH_MESSAGE);
  return info;
}

function tailHint(proc: BridgeProcess): string {
  const tail = proc.stderrTail(3);
  return tail.length > 0 ? `: ${tail.join(' | ')}` : '';
}

/** Fail fast if the process cannot spawn or exits before the handshake completes. */
function raceReady<T>(proc: BridgeProcess, work: Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    proc.once('spawn-error', (error: Error) => {
      reject(new Error(`could not start the Python bridge: ${error.message}`));
    });
    void proc.exit.then((exit) => {
      reject(new Error(`bridge exited before it was ready (exit ${exit.code ?? exit.signal})${tailHint(proc)}`));
    });
    work.then(resolve, reject);
  });
}

interface Session {
  readonly client: Bridge;
  readonly process: BridgeProcess | null;
  readonly info: InitializeResult;
}

export interface ControllerHooks {
  onStatus(status: BridgeStatus, info: InitializeResult | null, error: string | null, pid: number | undefined): void;
  onConnected(client: Bridge, info: InitializeResult): void;
  onCrash(report: CrashReport): void;
}

export class BridgeController {
  readonly #launch: BridgeLaunch;
  readonly #injected: Bridge | undefined;
  readonly #hooks: ControllerHooks;
  #session: Session | null = null;
  #lastProcess: BridgeProcess | null = null;
  #pending: Promise<Bridge> | null = null;
  #crashes: number[] = [];
  #stopping = false;
  #everReady = false;

  constructor(launch: BridgeLaunch, injected: Bridge | undefined, hooks: ControllerHooks) {
    this.#launch = launch;
    this.#injected = injected;
    this.#hooks = hooks;
  }

  /** The live client, connecting or respawning first when needed. */
  ensure(): Promise<Bridge> {
    if (this.#pending !== null) return this.#pending;
    if (this.#session !== null) return Promise.resolve(this.#session.client);
    const now = Date.now();
    this.#crashes = this.#crashes.filter((at) => now - at < CRASH_WINDOW_MS);
    if (this.#crashes.length >= 2) {
      return Promise.reject(new Error('The backend keeps stopping. Run /debug to see its stderr.'));
    }
    this.#pending = this.#connect().finally(() => {
      this.#pending = null;
    });
    return this.#pending;
  }

  stderrTail(count = 20): string[] {
    const proc = this.#session?.process ?? this.#lastProcess;
    return proc ? proc.stderrTail(count) : [];
  }

  get pid(): number | undefined {
    return (this.#session?.process ?? this.#lastProcess)?.pid;
  }

  /** Stop accepting crashes, send `shutdown` and escalate (SIGTERM, then SIGKILL). */
  async shutdown(): Promise<void> {
    this.#stopping = true;
    const session = this.#session;
    this.#session = null;
    if (session?.process) {
      await session.process.shutdown();
    } else {
      session?.client.close('shutdown');
    }
  }

  async #connect(): Promise<Bridge> {
    this.#hooks.onStatus('starting', null, null, undefined);
    try {
      const session = this.#injected
        ? { client: this.#injected, process: null, info: await handshake(this.#injected, this.#launch) }
        : await this.#spawn();
      this.#session = session;
      this.#everReady = true;
      this.#hooks.onStatus('ready', session.info, null, session.process?.pid);
      this.#hooks.onConnected(session.client, session.info);
      return session.client;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!this.#everReady) startFailure.message = message;
      this.#hooks.onStatus('failed', null, message, this.#lastProcess?.pid);
      throw error;
    }
  }

  async #spawn(): Promise<Session> {
    const proc = spawnBridge(spawnOptions(this.#launch));
    this.#lastProcess = proc;
    liveProcesses.add(proc);
    const client = new BridgeClient({
      readable: proc.child.stdout,
      writable: proc.child.stdin,
      timeouts: { ...DEFAULT_TIMEOUTS, default: DEFAULT_TIMEOUT_MS },
    });

    let ready = false;
    void proc.exit.then((exit) => {
      liveProcesses.delete(proc);
      client.close('bridge process exited');
      if (this.#session?.process === proc) this.#session = null;
      if (!ready || this.#stopping) return;
      this.#crashes.push(Date.now());
      this.#hooks.onCrash({ exit, stderrTail: proc.stderrTail(CRASH_TAIL_LINES) });
    });

    try {
      const info = await raceReady(proc, handshake(client, this.#launch));
      ready = true;
      return { client, process: proc, info };
    } catch (error) {
      client.close('handshake failed');
      await proc.shutdown().catch(() => undefined);
      throw error;
    }
  }
}

export interface BridgeHandle {
  readonly status: BridgeStatus;
  readonly info: InitializeResult | null;
  readonly error: string | null;
  readonly pid: number | undefined;
  ensure(): Promise<Bridge>;
  stderrTail(count?: number): string[];
  shutdown(): Promise<void>;
}

export interface UseBridgeOptions {
  readonly launch: BridgeLaunch;
  /** A ready-made bridge (snapshots and tests): no process is spawned. */
  readonly injected?: Bridge;
  readonly onConnected: (client: Bridge, info: InitializeResult) => void;
  readonly onCrash: (report: CrashReport) => void;
}

interface BridgeSnapshot {
  readonly status: BridgeStatus;
  readonly info: InitializeResult | null;
  readonly error: string | null;
  readonly pid: number | undefined;
}

export function useBridge(options: UseBridgeOptions): BridgeHandle {
  // Callbacks read the latest options, so a stale first render cannot call old handlers.
  const latest = useRef(options);
  latest.current = options;

  const [snapshot, setSnapshot] = useState<BridgeSnapshot>({
    status: 'starting',
    info: null,
    error: null,
    pid: undefined,
  });

  const [controller] = useState(
    () =>
      new BridgeController(options.launch, options.injected, {
        onStatus: (status, info, error, pid) => setSnapshot({ status, info, error, pid }),
        onConnected: (client, info) => latest.current.onConnected(client, info),
        onCrash: (report) => latest.current.onCrash(report),
      }),
  );

  useEffect(() => {
    controller.ensure().catch(() => undefined);
  }, [controller]);

  return {
    ...snapshot,
    ensure: () => controller.ensure(),
    stderrTail: (count) => controller.stderrTail(count),
    shutdown: () => controller.shutdown(),
  };
}
