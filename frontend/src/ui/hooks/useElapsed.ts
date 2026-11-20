/**
 * Elapsed time and spinner frame for the live region.
 * Ticks only while a run is active, so an idle app does not re-render.
 */
import { useEffect, useState } from 'react';

export const ELAPSED_TICK_MS = 100;

export interface Elapsed {
  /** Seconds since `startedAt`, 0 when inactive. */
  readonly seconds: number;
  /** Monotonic counter for the spinner; the caller takes it modulo the frame count. */
  readonly frame: number;
}

export function useElapsed(active: boolean, startedAt: number | null): Elapsed {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), ELAPSED_TICK_MS);
    return () => clearInterval(timer);
  }, [active]);

  const elapsedMs = active && startedAt !== null ? Math.max(0, now - startedAt) : 0;
  return { seconds: elapsedMs / 1000, frame: Math.floor(now / ELAPSED_TICK_MS) };
}
