import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';

import { BridgeClient } from '../src/bridge/client.js';
import {
  BridgeProcess,
  buildBridgeArgs,
  buildBridgeEnv,
  findPython,
  findRepoRoot,
  spawnBridge,
  type SpawnBridgeOptions,
} from '../src/bridge/process.js';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const repoRoot = path.resolve(frontendRoot, '..');
const stubPath = path.join(frontendRoot, 'test', 'fixtures', 'stub-bridge.mjs');

const spawned: BridgeProcess[] = [];
const tempDirs: string[] = [];

function tempDir(): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'finai-p3-'));
  tempDirs.push(dir);
  return dir;
}

function spawnStub(args: string[] = [], options: Partial<SpawnBridgeOptions> = {}): BridgeProcess {
  const child = spawnBridge({
    repoRoot,
    cwd: frontendRoot,
    python: { command: process.execPath, args: [] },
    moduleArgs: [stubPath, ...args],
    ...options,
  });
  spawned.push(child);
  return child;
}

function until(predicate: () => boolean, timeoutMs = 5_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const poll = (): void => {
      if (predicate()) {
        resolve();
        return;
      }
      if (Date.now() > deadline) {
        reject(new Error('timed out waiting for condition'));
        return;
      }
      setTimeout(poll, 2);
    };
    poll();
  });
}

const initializeParams = {
  protocol_version: 1,
  client: { name: 'finai-tui', version: '0.1.0' },
  terminal: { columns: 120, rows: 40 },
};

afterEach(async () => {
  for (const child of spawned.splice(0)) {
    child.signal('SIGKILL');
    await Promise.race([child.exit, new Promise((resolve) => setTimeout(resolve, 500))]);
  }
  for (const dir of tempDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe('python discovery', () => {
  it('walks up to the repository root', () => {
    expect(findRepoRoot(frontendRoot)).toBe(repoRoot);
    expect(findRepoRoot(path.join(frontendRoot, 'src', 'bridge'))).toBe(repoRoot);
    expect(() => findRepoRoot(tempDir())).toThrow(/pyproject\.toml/);
  });

  it('prefers $FINAI_PYTHON, then the repo venv, then uv', () => {
    expect(findPython(repoRoot, { FINAI_PYTHON: '/opt/python3' })).toEqual({
      command: '/opt/python3',
      args: [],
    });

    const noVenv = tempDir();
    expect(findPython(noVenv, {})).toEqual({
      command: 'uv',
      args: ['run', '--project', noVenv, 'python'],
    });
  });

  it('passes every bridge flag through and builds the child environment', () => {
    const options: SpawnBridgeOptions = {
      repoRoot: '/repo',
      dataDir: '.finai',
      session: 'abc123',
      replaySnapshots: '/tmp/snaps',
      fakeEvents: '/tmp/events.json',
      fakeDelayMs: 25,
    };
    expect(buildBridgeArgs(options)).toEqual([
      '-m',
      'finai.bridge',
      '--data-dir',
      '.finai',
      '--session',
      'abc123',
      '--replay-snapshots',
      '/tmp/snaps',
      '--fake-events',
      '/tmp/events.json',
      '--fake-delay-ms',
      '25',
    ]);
    expect(buildBridgeEnv(options, { PATH: '/bin' })).toMatchObject({
      PATH: '/bin',
      PYTHONPATH: path.join('/repo', 'backend'),
      PYTHONUNBUFFERED: '1',
    });
  });
});

describe('BridgeProcess', () => {
  it('spawns the bridge, initializes, logs stderr and shuts down cleanly', async () => {
    const dataDir = tempDir();
    const child = spawnStub([], { dataDir, session: 'session-1' });
    const client = new BridgeClient({ readable: child.child.stdout, writable: child.child.stdin });

    const result = await client.request('initialize', initializeParams);
    expect(result).toMatchObject({ protocol_version: 1, server_version: 'stub-0.0.0' });
    expect(result.session.id).toBe('stub-session');

    await until(() => child.stderrLines.some((line) => line.includes('received initialize')));
    expect(child.pid).toBeGreaterThan(0);
    expect(child.running).toBe(true);

    const exit = await child.shutdown({ sigtermAfterMs: 1_000, sigkillAfterMs: 1_000 });
    expect(exit.code).toBe(0);
    expect(child.running).toBe(false);

    const logPath = path.join(dataDir, 'logs', 'bridge.stderr.log');
    expect(child.stderrLogPath).toBe(logPath);
    await until(() => readFileSync(logPath, 'utf8').includes('received shutdown'));
    expect(readFileSync(logPath, 'utf8')).toContain('stub-bridge: started pid=');
    client.close();
  });

  it('escalates shutdown to SIGKILL when the child ignores shutdown and SIGTERM', async () => {
    const child = spawnStub(['--ignore-shutdown', '--ignore-sigterm'], {
      stderrLog: false,
      sigtermAfterMs: 100,
      sigkillAfterMs: 100,
    });
    const startedAt = Date.now();
    const exit = await child.shutdown();
    expect(exit.code).toBeNull();
    expect(exit.signal).toBe('SIGKILL');
    expect(Date.now() - startedAt).toBeLessThan(3_000);
  });

  it('escalates to SIGTERM when the child ignores shutdown but not signals', async () => {
    const child = spawnStub(['--ignore-shutdown'], { stderrLog: false, sigtermAfterMs: 50, sigkillAfterMs: 5_000 });
    const exit = await child.shutdown();
    expect(exit.signal).toBe('SIGTERM');
  });

  it('reports an unexpected crash through the exit event', async () => {
    const child = spawnStub(['--crash-on-initialize'], { stderrLog: false });
    const exits: Array<number | null> = [];
    child.on('exit', (code: number | null) => exits.push(code));

    await new Promise<void>((resolve) => {
      child.child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} })}\n`);
      child.exit.then(() => resolve());
    });

    expect(exits).toEqual([3]);
    await until(() => child.stderrLines.some((line) => line.includes('received initialize')));
    await expect(child.exit).resolves.toEqual({ code: 3, signal: null });
  });

  it('emits exit for a startup crash', async () => {
    const child = spawnStub(['--crash-immediately'], { stderrLog: false });
    await expect(child.exit).resolves.toEqual({ code: 7, signal: null });
  });

  it('keeps only the last N stderr lines in the ring buffer', async () => {
    const child = spawnStub(['--stderr-lines', '8'], { stderrLog: false, stderrRingSize: 5 });
    await until(() => child.stderrLines.length === 5 && (child.stderrLines.at(-1) ?? '').includes('noise 8'));
    expect(child.stderrLines).toHaveLength(5);
    expect(child.stderrLines.at(-1)).toContain('noise 8');
    expect(child.stderrTail(2)).toHaveLength(2);
  });
});
