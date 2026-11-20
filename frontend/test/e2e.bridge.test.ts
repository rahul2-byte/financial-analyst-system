/**
 * Real Python bridge, fake provider events. Needs the repo .venv; skipped otherwise.
 * No network and no provider keys: `--fake-events` replays the HDFC fixture.
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';

import type { InitializeResult } from '../src/protocol/generated.js';
import { PROTOCOL_VERSION } from '../src/protocol/version.js';
import { BridgeController, type BridgeLaunch } from '../src/ui/hooks/useBridge.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..', '..');
const python = path.join(repoRoot, '.venv', 'bin', 'python');
const fixture = path.join(repoRoot, 'backend', 'tests', 'fixtures', 'hdfc_run_events.json');
const hasPython = existsSync(python) && existsSync(fixture);

const launch: BridgeLaunch = {
  repoRoot,
  cwd: repoRoot,
  columns: 100,
  rows: 30,
};

describe.skipIf(!hasPython)('real bridge handshake (fake events)', () => {
  const previous = process.env.FINAI_BRIDGE_CMD;
  let controller: BridgeController | undefined;

  afterEach(async () => {
    await controller?.shutdown();
    controller = undefined;
    if (previous === undefined) delete process.env.FINAI_BRIDGE_CMD;
    else process.env.FINAI_BRIDGE_CMD = previous;
  });

  it('starts the Python bridge and completes initialize with protocol_version checked', async () => {
    process.env.FINAI_BRIDGE_CMD = `${python} -m finai.bridge --fake-events ${fixture}`;
    const connected: InitializeResult[] = [];
    controller = new BridgeController(launch, undefined, {
      onStatus: () => undefined,
      onConnected: (_client, info) => {
        connected.push(info);
      },
      onCrash: () => undefined,
    });
    const client = await controller.ensure();
    expect(client).toBeDefined();
    expect(connected).toHaveLength(1);
    expect(connected[0]?.protocol_version).toBe(PROTOCOL_VERSION);
    expect(controller.pid).toBeGreaterThan(0);
  }, 30_000);
});
