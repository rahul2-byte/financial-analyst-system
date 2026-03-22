import "@testing-library/jest-dom/vitest";

if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = (cb: FrameRequestCallback): number => {
    return setTimeout(() => cb(performance.now()), 16) as unknown as number;
  };
}

if (!globalThis.cancelAnimationFrame) {
  globalThis.cancelAnimationFrame = (id: number): void => {
    clearTimeout(id);
  };
}
