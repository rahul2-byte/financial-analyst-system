import { readFileSync, readdirSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { Display, ResearchEvent } from '../src/protocol/generated.js';
import { reduceEvent } from '../src/state/reducer.js';
import { initialState, toGoldenJSON } from '../src/state/types.js';

interface GoldenEvent {
  event: ResearchEvent;
  display: Display | null;
}

interface GoldenFile {
  events: GoldenEvent[];
  snapshots: { after_sequence: number; state: unknown }[];
  final: unknown;
}

const GOLDEN_DIR = new URL('./goldens/', import.meta.url);

const GOLDEN_FILES = readdirSync(GOLDEN_DIR)
  .filter((name) => name.endsWith('.json') && name !== 'sanitize_cases.json')
  .sort();

/** Recursively sort object keys so `JSON.stringify` output is comparable to Python's sort_keys. */
function sortKeysDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeysDeep);
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      out[key] = sortKeysDeep((value as Record<string, unknown>)[key]);
    }
    return out;
  }
  return value;
}

describe('reducer goldens', () => {
  it('found the golden files', () => {
    expect(GOLDEN_FILES.length).toBeGreaterThanOrEqual(10);
  });

  for (const file of GOLDEN_FILES) {
    describe(file, () => {
      const golden = JSON.parse(readFileSync(new URL(file, GOLDEN_DIR), 'utf8')) as GoldenFile;

      it('has one snapshot per event', () => {
        expect(golden.snapshots).toHaveLength(golden.events.length);
      });

      it('matches every snapshot in order', () => {
        let state = initialState();
        golden.events.forEach((entry, index) => {
          state = reduceEvent(state, entry.event, entry.display);
          const snapshot = golden.snapshots[index];
          const where = `${file} after event ${index + 1} (sequence ${entry.event.meta.sequence})`;
          expect(snapshot?.after_sequence, where).toBe(entry.event.meta.sequence);
          expect(toGoldenJSON(state), where).toStrictEqual(snapshot?.state);
          expect(JSON.stringify(toGoldenJSON(state)), where).toBe(
            JSON.stringify(sortKeysDeep(snapshot?.state)),
          );
        });
      });

      it('matches the final state', () => {
        let state = initialState();
        for (const entry of golden.events) {
          state = reduceEvent(state, entry.event, entry.display);
        }
        expect(toGoldenJSON(state)).toStrictEqual(golden.final);
      });
    });
  }

  it('ignores a duplicate sequence and returns the same state object', () => {
    const golden = JSON.parse(
      readFileSync(new URL('out_of_order_duplicates.json', GOLDEN_DIR), 'utf8'),
    ) as GoldenFile;
    const first = golden.events[0];
    expect(first).toBeDefined();
    if (!first) return;
    const once = reduceEvent(initialState(), first.event, first.display);
    expect(reduceEvent(once, first.event, first.display)).toBe(once);
  });
});
