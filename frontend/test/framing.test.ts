import { PassThrough, Writable } from 'node:stream';
import { describe, expect, it } from 'vitest';

import { FramingError, LineReader, writeMessage } from '../src/bridge/framing.js';

function collect(maxLineBytes?: number) {
  const lines: string[] = [];
  const errors: FramingError[] = [];
  const reader = new LineReader({
    onLine: (line) => lines.push(line),
    onError: (error) => errors.push(error),
    ...(maxLineBytes === undefined ? {} : { maxLineBytes }),
  });
  return { reader, lines, errors };
}

describe('LineReader', () => {
  it('emits one line per newline and keeps partial lines buffered', () => {
    const { reader, lines } = collect();
    reader.push('{"a":1}\n{"b":2}\n{"c":');
    expect(lines).toEqual(['{"a":1}', '{"b":2}']);
    expect(reader.bufferedBytes).toBe(5);
    reader.push('3}\n');
    expect(lines).toEqual(['{"a":1}', '{"b":2}', '{"c":3}']);
  });

  it('reassembles a line split across arbitrary chunks', () => {
    const payload = JSON.stringify({ type: 'run.started', query: 'HDFC Bank fundamentals' });
    const wire = `${payload}\n${payload}\n`;
    const { reader, lines } = collect();
    for (const char of wire) reader.push(char);
    expect(lines).toEqual([payload, payload]);
  });

  it('decodes multi-byte UTF-8 split across chunk boundaries', () => {
    const text = 'héllo — ₹ 4,20,000 · ✓ 😀 終';
    const payload = JSON.stringify({ text });
    const wire = Buffer.from(`${payload}\n`, 'utf8');

    for (let split = 1; split < wire.length; split += 1) {
      const { reader, lines, errors } = collect();
      reader.push(wire.subarray(0, split));
      reader.push(wire.subarray(split));
      expect(errors).toEqual([]);
      expect(lines).toEqual([payload]);
      expect(JSON.parse(lines[0] as string)).toEqual({ text });
    }
  });

  it('tolerates CRLF and blank lines', () => {
    const { reader, lines } = collect();
    reader.push('{"a":1}\r\n\r\n{"b":2}\n');
    expect(lines).toEqual(['{"a":1}', '{"b":2}']);
  });

  it('drops an oversize line, reports one error and keeps reading', () => {
    const { reader, lines, errors } = collect(16);
    reader.push('x'.repeat(10));
    reader.push(`${'y'.repeat(10)}\n{"ok":true}\n`);
    expect(lines).toEqual(['{"ok":true}']);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.code).toBe(-32700);
    expect(reader.dropping).toBe(false);
  });

  it('drops an oversize line contained in a single chunk', () => {
    const { reader, lines, errors } = collect(8);
    reader.push(`${'a'.repeat(9)}\nnext\n`);
    expect(lines).toEqual(['next']);
    expect(errors).toHaveLength(1);
  });

  it('allows a line exactly at the limit', () => {
    const { reader, lines, errors } = collect(4);
    reader.push('abcd\nabcde\n');
    expect(lines).toEqual(['abcd']);
    expect(errors).toHaveLength(1);
  });
});

describe('writeMessage', () => {
  it('writes compact single-line JSON terminated by a newline', async () => {
    const chunks: Buffer[] = [];
    const sink = new Writable({
      write(chunk: Buffer, _encoding, callback) {
        chunks.push(Buffer.from(chunk));
        callback();
      },
    });

    await writeMessage(sink, { jsonrpc: '2.0', id: 1, method: 'initialize', params: { a: [1, 2] } });
    const wire = Buffer.concat(chunks).toString('utf8');
    expect(wire.endsWith('\n')).toBe(true);
    expect(wire.trimEnd().includes('\n')).toBe(false);
    expect(wire).toBe('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"a":[1,2]}}\n');
  });

  it('honours backpressure until the stream drains', async () => {
    const sink = new PassThrough({ highWaterMark: 1 });
    const pending = writeMessage(sink, { type: 'run.event', text: 'x'.repeat(64) });
    expect(sink.writableLength).toBeGreaterThan(0);
    const drained: string[] = [];
    sink.on('data', (chunk: Buffer) => drained.push(chunk.toString('utf8')));
    await pending;
    expect(drained.join('')).toContain('"type":"run.event"');
  });

  it('rejects on a closed stream', async () => {
    const sink = new Writable({ write: (_chunk, _encoding, callback) => callback() });
    sink.end();
    await expect(writeMessage(sink, { a: 1 })).rejects.toBeInstanceOf(FramingError);
  });
});
