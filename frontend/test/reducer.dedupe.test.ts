import { describe, expect, it } from 'vitest';

import { reduceEvent } from '../src/state/reducer.js';
import { initialState } from '../src/state/types.js';
import type { ResearchEvent } from '../src/protocol/generated.js';

function delta(sequence: number, text: string): ResearchEvent {
  return { type: 'response.delta', text, meta: { sequence, run_id: 'r' } } as unknown as ResearchEvent;
}

describe('reducer sequence dedupe', () => {
  it('ignores a repeated sequence and returns the same state object', () => {
    const s1 = reduceEvent(initialState(), delta(1, 'a'), null);
    const s2 = reduceEvent(s1, delta(1, 'a'), null);
    expect(s2).toBe(s1);
    expect(s2.responseText).toBe('a');
  });

  it('records every sequence and the latest one', () => {
    let s = initialState();
    for (const n of [1, 3, 2]) s = reduceEvent(s, delta(n, String(n)), null);
    expect([...s.seenSequences].sort()).toEqual([1, 2, 3]);
    expect(s.latestSequence).toBe(3);
    expect(s.responseText).toBe('132');
    expect(reduceEvent(s, delta(2, 'x'), null)).toBe(s);
  });

  it('does not share seen sequences between independent runs', () => {
    const a = reduceEvent(initialState(), delta(1, 'a'), null);
    const b = reduceEvent(initialState(), delta(1, 'b'), null);
    expect(b.responseText).toBe('b');
    expect(a.responseText).toBe('a');
  });

  it('applies 3000 deltas in linear time', () => {
    let s = initialState();
    const start = performance.now();
    for (let i = 1; i <= 3000; i++) s = reduceEvent(s, delta(i, 'x'), null);
    expect(s.responseText.length).toBe(3000);
    expect(s.seenSequences.size).toBe(3000);
    expect(performance.now() - start).toBeLessThan(1000);
  });
});
