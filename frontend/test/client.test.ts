import { PassThrough } from 'node:stream';
import { afterEach, describe, expect, it } from 'vitest';

import { BridgeClient, BridgeError, BridgeTimeoutError, INTERNAL_ERROR } from '../src/bridge/client.js';
import { LineReader } from '../src/bridge/framing.js';

type WireMessage = Record<string, unknown>;

function until(predicate: () => boolean, timeoutMs = 2_000): Promise<void> {
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
      setTimeout(poll, 1);
    };
    poll();
  });
}

function harness(
  options: {
    timeouts?: Record<string, number>;
    onProtocolError?: (error: Error) => void;
    onUnknownNotification?: (method: string, params: unknown) => void;
    firstRequestId?: number;
  } = {},
) {
  const inbound = new PassThrough();
  const outbound = new PassThrough();
  const written: WireMessage[] = [];
  const reader = new LineReader({ onLine: (line) => written.push(JSON.parse(line) as WireMessage) });
  outbound.on('data', (chunk: Buffer) => reader.push(chunk));

  const client = new BridgeClient({
    readable: inbound,
    writable: outbound,
    ...options,
  });

  return {
    client,
    inbound,
    written,
    respond(id: number, result: unknown) {
      inbound.write(`${JSON.stringify({ jsonrpc: '2.0', id, result })}\n`);
    },
    respondError(id: number, error: unknown) {
      inbound.write(`${JSON.stringify({ jsonrpc: '2.0', id, error })}\n`);
    },
    notify(method: string, params: unknown) {
      inbound.write(`${JSON.stringify({ jsonrpc: '2.0', method, params })}\n`);
    },
    writeRaw(text: string) {
      inbound.write(text);
    },
  };
}

const initializeParams = {
  protocol_version: 1,
  client: { name: 'finai-tui', version: '0.1.0' },
  terminal: { columns: 120, rows: 40 },
};

afterEach(() => {
  // Every test closes its client implicitly through GC; nothing global to clean.
});

describe('BridgeClient requests', () => {
  it('writes a JSON-RPC request with an integer id and resolves the response', async () => {
    const harnessed = harness();
    const pending = harnessed.client.request('initialize', initializeParams);

    await until(() => harnessed.written.length === 1);
    expect(harnessed.written[0]).toEqual({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: initializeParams,
    });

    harnessed.respond(1, { protocol_version: 1, server_version: '0.1.0' });
    await expect(pending).resolves.toEqual({ protocol_version: 1, server_version: '0.1.0' });
    expect(harnessed.client.pendingCount).toBe(0);
  });

  it('matches out-of-order responses to their own requests', async () => {
    const harnessed = harness();
    const first = harnessed.client.request('session.history', {});
    const second = harnessed.client.request('session.list', { limit: 5 });

    await until(() => harnessed.written.length === 2);
    expect(harnessed.written.map((message) => message.id)).toEqual([1, 2]);

    harnessed.respond(2, { sessions: [{ id: 'second' }] });
    harnessed.respond(1, { queries: ['first'] });

    await expect(second).resolves.toEqual({ sessions: [{ id: 'second' }] });
    await expect(first).resolves.toEqual({ queries: ['first'] });
  });

  it('maps a JSON-RPC error response to BridgeError with code, message and data', async () => {
    const harnessed = harness();
    const pending = harnessed.client.request('session.resume', { id_prefix: 'abc' });
    await until(() => harnessed.written.length === 1);

    harnessed.respondError(1, { code: -32003, message: 'no such session', data: { matches: ['abc1'] } });

    const error = await pending.catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(BridgeError);
    expect(error).toMatchObject({ code: -32003, message: 'no such session', data: { matches: ['abc1'] } });
  });

  it('rejects with BridgeTimeoutError and clears the pending entry', async () => {
    const harnessed = harness({ timeouts: { default: 10 } });
    const pending = harnessed.client.request('session.history', {});

    await expect(pending).rejects.toBeInstanceOf(BridgeTimeoutError);
    expect(harnessed.client.pendingCount).toBe(0);
    // A late response for a timed-out id is reported, not swallowed silently.
    const errors: Error[] = [];
    const second = harness({ onProtocolError: (error) => errors.push(error) });
    void second.client.request('session.history', {}, { timeoutMs: 5 }).catch(() => undefined);
    await until(() => second.written.length === 1);
    // Wait for the request to time out so the response is genuinely late.
    await until(() => second.client.pendingCount === 0);
    second.respond(1, { queries: [] });
    await until(() => errors.length === 1);
    expect(errors[0]?.message).toContain('unknown request id 1');
  });

  it('starts ids at firstRequestId when configured', async () => {
    const harnessed = harness({ firstRequestId: 41 });
    void harnessed.client.request('session.history', {}).catch(() => undefined);
    await until(() => harnessed.written.length === 1);
    expect(harnessed.written[0]?.id).toBe(41);
    harnessed.client.close();
  });

  it('rejects pending requests on close and refuses new ones', async () => {
    const harnessed = harness();
    const pending = harnessed.client.request('trace.tail', { limit: 3 });
    harnessed.client.close('bye');

    await expect(pending).rejects.toMatchObject({ code: INTERNAL_ERROR, message: 'bye' });
    await expect(harnessed.client.request('trace.tail', { limit: 3 })).rejects.toBeInstanceOf(BridgeError);
    expect(harnessed.client.closed).toBe(true);
  });

  it('fails pending requests when the transport ends', async () => {
    const harnessed = harness();
    const pending = harnessed.client.request('context.info', {});
    await until(() => harnessed.written.length === 1);

    harnessed.inbound.end();

    await expect(pending).rejects.toMatchObject({ message: 'bridge stream closed' });
    expect(harnessed.client.pendingCount).toBe(0);
    harnessed.client.close();
  });
});

describe('BridgeClient notifications', () => {
  it('fans out notifications to every handler and honours unsubscribe', async () => {
    const harnessed = harness();
    const seen: string[] = [];
    const offA = harnessed.client.on('run.event', (params) => seen.push(`a:${params.client_run_id}`));
    harnessed.client.on('run.event', (params) => seen.push(`b:${params.client_run_id}`));

    harnessed.notify('run.event', { client_run_id: 'run-1', event: { type: 'run.started' }, display: null });
    await until(() => seen.length === 2);
    expect(seen).toEqual(['a:run-1', 'b:run-1']);

    offA();
    harnessed.notify('run.event', { client_run_id: 'run-2', event: { type: 'run.started' }, display: null });
    await until(() => seen.length === 3);
    expect(seen).toEqual(['a:run-1', 'b:run-1', 'b:run-2']);
  });

  it('reports malformed frames and unknown notifications instead of throwing', async () => {
    const protocolErrors: Error[] = [];
    const unknown: Array<[string, unknown]> = [];
    const harnessed = harness({
      onProtocolError: (error) => protocolErrors.push(error),
      onUnknownNotification: (method, params) => unknown.push([method, params]),
    });

    harnessed.writeRaw('not json\n');
    harnessed.writeRaw('{"jsonrpc":"2.0","method":"run.event","params":{"client_run_id":"x"}}\n');
    harnessed.writeRaw('{"jsonrpc":"2.0","method":"future.method","params":{"n":1}}\n');
    harnessed.writeRaw('{"jsonrpc":"2.0"}\n');

    await until(() => protocolErrors.length === 2 && unknown.length === 2);
    expect(protocolErrors[0]?.name).toBe('FramingError');
    expect(unknown.map(([method]) => method)).toEqual(['run.event', 'future.method']);
    // Registered handlers suppress the unknown-notification callback.
    harnessed.client.on('run.event', () => undefined);
    harnessed.notify('run.event', { client_run_id: 'y' });
    await until(() => protocolErrors.length === 2 && unknown.length === 2);
    expect(unknown).toHaveLength(2);
  });

  it('keeps working when a notification handler throws', async () => {
    const protocolErrors: Error[] = [];
    const harnessed = harness({ onProtocolError: (error) => protocolErrors.push(error) });
    const seen: string[] = [];
    harnessed.client.on('bridge.log', () => {
      throw new Error('handler exploded');
    });
    harnessed.client.on('bridge.log', (params) => seen.push(params.message));

    harnessed.notify('bridge.log', { level: 'warning', message: 'still delivered' });
    await until(() => seen.length === 1 && protocolErrors.length === 1);
    expect(seen).toEqual(['still delivered']);
    expect(protocolErrors[0]?.message).toBe('handler exploded');
  });

  it('reassembles a response split across chunks', async () => {
    const harnessed = harness();
    const pending = harnessed.client.request('session.history', {});
    await until(() => harnessed.written.length === 1);
    const wire = `${JSON.stringify({ jsonrpc: '2.0', id: 1, result: { queries: ['a', 'b'] } })}\n`;
    harnessed.writeRaw(wire.slice(0, 12));
    harnessed.writeRaw(wire.slice(12));
    await expect(pending).resolves.toEqual({ queries: ['a', 'b'] });
  });
});
