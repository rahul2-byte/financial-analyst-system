/**
 * External store for the presentation state.
 *
 * `dispatch` runs the reducer immediately, so `getState()` is always current.
 * Listeners are notified at most once per `THROTTLE_MS`: the first change in a
 * quiet window notifies at once (leading), and changes inside the window collapse
 * into one notification at its end (trailing). `flushNow()` notifies at once if a
 * change is pending. Keystrokes never go through this store, so they are not delayed.
 *
 * Use with React as `useSyncExternalStore(store.subscribe, store.getState)`.
 */
import type { Display, ResearchEvent } from '../protocol/generated.js';
import { reduceEvent, localPhase } from './reducer.js';
import { initialState, type PresentationState, type UiSetPhase } from './types.js';

export const THROTTLE_MS = 33;

export interface Store<S, A> {
  getState(): S;
  dispatch(action: A): void;
  subscribe(listener: () => void): () => void;
  /** Notify now if a change is pending (e.g. at run end, so the final frame is not held back). */
  flushNow(): void;
}

export function createThrottledStore<S, A>(
  initial: S,
  reduce: (state: S, action: A) => S,
  throttleMs: number = THROTTLE_MS,
): Store<S, A> {
  let state = initial;
  const listeners = new Set<() => void>();
  let lastNotifyAt = Number.NEGATIVE_INFINITY;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending = false;

  function notify(): void {
    pending = false;
    lastNotifyAt = Date.now();
    for (const listener of [...listeners]) listener();
  }

  function clearTimer(): void {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function scheduleNotify(): void {
    pending = true;
    const elapsed = Date.now() - lastNotifyAt;
    if (elapsed >= throttleMs) {
      clearTimer();
      notify();
      return;
    }
    if (timer === null) {
      timer = setTimeout(() => {
        timer = null;
        if (pending) notify();
      }, throttleMs - elapsed);
    }
  }

  return {
    getState: () => state,
    dispatch(action) {
      const next = reduce(state, action);
      if (Object.is(next, state)) return;
      state = next;
      scheduleNotify();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    flushNow() {
      if (!pending) return;
      clearTimer();
      notify();
    },
  };
}

export type PresentationAction =
  | { type: 'event'; event: ResearchEvent; display: Display | null }
  | { type: 'local-phase'; phase: UiSetPhase };

export function presentationReducer(state: PresentationState, action: PresentationAction): PresentationState {
  if (action.type === 'event') return reduceEvent(state, action.event, action.display);
  return localPhase(state, action.phase);
}

export function createPresentationStore(
  initial: PresentationState = initialState(),
  throttleMs: number = THROTTLE_MS,
): Store<PresentationState, PresentationAction> {
  return createThrottledStore(initial, presentationReducer, throttleMs);
}
