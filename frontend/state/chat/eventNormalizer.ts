import type { StreamEvent } from "@/types";

type UnknownRecord = Record<string, unknown>;

function isObject(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null;
}

export function normalizeStreamEvent(raw: unknown): StreamEvent {
  if (!isObject(raw)) {
    return { type: "error", message: "Invalid stream payload" };
  }

  const directType = raw.type;
  if (typeof directType === "string") {
    return raw as StreamEvent;
  }

  const legacyType = raw.event;
  const legacyData = isObject(raw.data) ? raw.data : {};
  if (typeof legacyType === "string") {
    return {
      type: legacyType as StreamEvent["type"],
      ...(legacyData as UnknownRecord),
    } as StreamEvent;
  }

  return { type: "error", message: "Unsupported stream payload shape" };
}
