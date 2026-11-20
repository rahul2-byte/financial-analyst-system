import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Display, ResearchEvent } from '../src/protocol/generated.js';
import { THROTTLE_MS, createPresentationStore, createThrottledStore } from '../src/state/store.js';

function sumStore() {
  return createThrottledStore(0, (state: number, action: number) => (action === 0 ? state : state + action), THROTTLE_MS);
}

interface GoldenEvent {
  event: ResearchEvent;
  display: Display | null;
}

describe('createThrottledStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('uses a 33 ms throttle', () => {
    expect(THROTTLE_MS).toBe(33);
  });

  it('notifies at once for a change after a quiet window (leading edge)', () => {
    const store = sumStore();
    const listener = vi.fn();
    store.subscribe(listener);
    store.dispatch(1);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getState()).toBe(1);
  });

  it('collapses changes inside the window into one trailing notification', () => {
    const store = sumStore();
    const listener = vi.fn();
    store.subscribe(listener);
    store.dispatch(1);
    expect(listener).toHaveBeenCalledTimes(1);

    store.dispatch(2);
    store.dispatch(3);
    store.dispatch(4);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getState()).toBe(10);

    vi.advanceTimersByTime(32);
    expect(listener).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(listener).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(1000);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('getState is current even while notifications are throttled', () => {
    const store = sumStore();
    store.dispatch(5);
    store.dispatch(5);
    expect(store.getState()).toBe(10);
  });

  it('does not notify when the reducer returns the same state', () => {
    const store = sumStore();
    const listener = vi.fn();
    store.subscribe(listener);
    store.dispatch(0);
    vi.advanceTimersByTime(THROTTLE_MS * 2);
    expect(listener).not.toHaveBeenCalled();
  });

  it('flushNow notifies a pending change at once and is idempotent', () => {
    const store = sumStore();
    const listener = vi.fn();
    store.subscribe(listener);
    store.dispatch(1);
    store.dispatch(2);
    expect(listener).toHaveBeenCalledTimes(1);

    store.flushNow();
    expect(listener).toHaveBeenCalledTimes(2);

    store.flushNow();
    expect(listener).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(THROTTLE_MS * 2);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('flushNow does nothing when nothing is pending', () => {
    const store = sumStore();
    const listener = vi.fn();
    store.subscribe(listener);
    store.flushNow();
    expect(listener).not.toHaveBeenCalled();
  });

  it('unsubscribe stops notifications', () => {
    const store = sumStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    unsubscribe();
    store.dispatch(1);
    vi.advanceTimersByTime(THROTTLE_MS * 2);
    expect(listener).not.toHaveBeenCalled();
  });

  it('a listener subscribed in a quiet window gets the leading notification on the next change', () => {
    const store = sumStore();
    store.dispatch(1);
    vi.advanceTimersByTime(THROTTLE_MS);
    const listener = vi.fn();
    store.subscribe(listener);
    store.dispatch(1);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('createPresentationStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('dispatches reducer actions and keeps getState current', () => {
    const golden = JSON.parse(
      readFileSync(new URL('./goldens/out_of_order_duplicates.json', import.meta.url), 'utf8'),
    ) as { events: GoldenEvent[] };
    const first = golden.events[0];
    expect(first).toBeDefined();
    if (!first) return;

    const store = createPresentationStore();
    const listener = vi.fn();
    store.subscribe(listener);
    store.dispatch({ type: 'event', event: first.event, display: first.display });
    expect(store.getState().latestSequence).toBe(first.event.meta.sequence);
    expect(listener).toHaveBeenCalledTimes(1);

    store.dispatch({ type: 'event', event: first.event, display: first.display });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('applies local phase actions', () => {
    const store = createPresentationStore();
    store.dispatch({ type: 'local-phase', phase: 'cancelling' });
    expect(store.getState().phase).toBe('cancelling');
  });
});
