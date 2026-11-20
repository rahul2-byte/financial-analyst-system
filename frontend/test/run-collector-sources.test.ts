/** Sources accumulate across `sources.updated` events and are deduped, not overwritten. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import type { Display, ResearchEvent } from '../src/protocol/generated.js';
import { createPresentationStore } from '../src/state/store.js';
import { RunCollector } from '../src/ui/App.js';

const GOLDEN = path.join(path.dirname(fileURLToPath(import.meta.url)), 'goldens', 'hdfc_run.json');

describe('RunCollector sources', () => {
  it('keeps every distinct source of the HDFC run, deduped, and counts them in the footer', () => {
    const golden = JSON.parse(readFileSync(GOLDEN, 'utf8')) as {
      events: Array<{ event: ResearchEvent; display: Display | null }>;
    };
    const collector = new RunCollector({
      clientRunId: 'r1',
      query: 'HDFCBANK',
      store: createPresentationStore(undefined, 0),
    });
    for (const { event, display } of golden.events) collector.onEvent(event, display);
    // Four sources.updated events, one repeat (Upstox twice): three distinct sources.
    expect(collector.sources.map((source) => source.label)).toEqual([
      'Upstox',
      'Yahoo Finance · price history · HDFCBANK.NS',
      'upstox.com',
    ]);
    const items = collector.onFinished({ client_run_id: 'r1', outcome: 'completed' } as never);
    const footer = items.find((item) => item.kind === 'run-footer');
    expect(footer).toMatchObject({ sourceCount: 3 });
  });
});
