import { describe, expect, it } from "vitest";

import { normalizeStreamEvent } from "@/state/chat/eventNormalizer";

describe("normalizeStreamEvent", () => {
  it("returns already-flat event shape unchanged", () => {
    const event = { type: "status", message: "ok" };
    expect(normalizeStreamEvent(event)).toEqual(event);
  });

  it("normalizes legacy nested payload shape", () => {
    const legacy = {
      event: "error",
      data: {
        message: "boom",
      },
    };

    expect(normalizeStreamEvent(legacy)).toEqual({
      type: "error",
      message: "boom",
    });
  });
});
