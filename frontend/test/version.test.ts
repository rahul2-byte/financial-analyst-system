import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import type { ResearchEvent } from '../src/protocol/events.js';
import { isResearchEvent, isResearchEventType, RESEARCH_EVENT_TYPES } from '../src/protocol/events.js';
import { PROTOCOL_MISMATCH_MESSAGE, PROTOCOL_VERSION } from '../src/protocol/version.js';

const protocolSchemaPath = new URL('../../protocol/schema/protocol.schema.json', import.meta.url);
const eventSchemaPath = new URL('../../protocol/schema/research_event.schema.json', import.meta.url);

interface DiscriminatedSchema {
  title?: string;
  discriminator?: { propertyName: string; mapping: Record<string, string> };
  oneOf?: unknown[];
}

const protocolSchema = JSON.parse(readFileSync(protocolSchemaPath, 'utf8')) as DiscriminatedSchema;
const eventSchema = JSON.parse(readFileSync(eventSchemaPath, 'utf8')) as DiscriminatedSchema;

const meta = {
  event_id: '2f1c6a1e-2b6d-4c4b-9c2f-0e6a3c1f9a11',
  run_id: '2f1c6a1e-2b6d-4c4b-9c2f-0e6a3c1f9a12',
  conversation_id: '2f1c6a1e-2b6d-4c4b-9c2f-0e6a3c1f9a13',
  sequence: 1,
  occurred_at: '2026-11-21T10:00:00Z',
};

describe('protocol version', () => {
  it('is v1 and matches the schema title', () => {
    expect(PROTOCOL_VERSION).toBe(1);
    expect(protocolSchema.title).toBe(`FIN-AI bridge protocol v${PROTOCOL_VERSION}`);
  });

  it('documents the mismatch remedy', () => {
    expect(PROTOCOL_MISMATCH_MESSAGE).toBe(
      'Frontend and backend are out of sync. Run: uv sync && npm --prefix frontend run build',
    );
  });
});

describe('ResearchEvent union', () => {
  it('covers every discriminated variant in the schema, in schema order', () => {
    const schemaTypes = Object.keys(eventSchema.discriminator?.mapping ?? {});
    expect(schemaTypes).toHaveLength(27);
    expect([...RESEARCH_EVENT_TYPES]).toEqual(schemaTypes);
    expect(eventSchema.oneOf).toHaveLength(schemaTypes.length);
    expect(eventSchema.discriminator?.propertyName).toBe('type');
  });

  it('narrows on the `type` discriminant', () => {
    const started: ResearchEvent = { type: 'run.started', meta, query: 'HDFC Bank fundamentals' };
    const failed: ResearchEvent = { type: 'tool.failed', meta, tool: 'data:fetch', message: 'timeout' };

    const describe = (event: ResearchEvent): string => {
      switch (event.type) {
        case 'run.started':
          return `started:${event.query}`;
        case 'tool.failed':
          return `failed:${event.message}`;
        default:
          return event.type;
      }
    };

    expect(describe(started)).toBe('started:HDFC Bank fundamentals');
    expect(describe(failed)).toBe('failed:timeout');
  });

  it('guards untrusted payloads', () => {
    expect(isResearchEventType('response.delta')).toBe(true);
    expect(isResearchEventType('future.event')).toBe(false);
    expect(isResearchEvent({ type: 'run.started', meta, query: 'q' })).toBe(true);
    expect(isResearchEvent({ type: 'future.event' })).toBe(false);
    expect(isResearchEvent(null)).toBe(false);
    expect(isResearchEvent('run.started')).toBe(false);
  });
});
