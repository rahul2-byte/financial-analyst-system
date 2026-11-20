/**
 * `ResearchEvent` as a TS union discriminated on `type`.
 *
 * `json-schema-to-typescript` already emits a discriminated union for the
 * `oneOf` + `discriminator` root of `research_event.schema.json`, so this module
 * only re-exports it (no hand-written field shapes). The per-variant interfaces
 * live in `generated.ts`.
 */
export type { ResearchEvent } from './generated.js';

import type { ResearchEvent } from './generated.js';

/** Discriminant values of every event variant, in schema order. */
export const RESEARCH_EVENT_TYPES = [
  'approval.requested',
  'approval.resolved',
  'check.stage',
  'clarification.requested',
  'context.compacted',
  'model.request.started',
  'model.response.completed',
  'provider.attempt.started',
  'provider.completed',
  'provider.failed',
  'provider.retrying',
  'provider.stream.started',
  'response.delta',
  'route.decision.made',
  'run.cancelled',
  'run.completed',
  'run.failed',
  'run.started',
  'skill.selected',
  'sources.updated',
  'stage.completed',
  'stage.failed',
  'stage.started',
  'tool.completed',
  'tool.failed',
  'tool.progress',
  'tool.started',
] as const satisfies readonly ResearchEvent['type'][];

export type ResearchEventType = (typeof RESEARCH_EVENT_TYPES)[number];

const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set<string>(RESEARCH_EVENT_TYPES);

/** Narrow an unknown event `type` string; unknown types are ignored by the UI. */
export function isResearchEventType(type: string): type is ResearchEventType {
  return KNOWN_EVENT_TYPES.has(type);
}

/** Narrow an untrusted payload to `ResearchEvent` by discriminant only. */
export function isResearchEvent(value: unknown): value is ResearchEvent {
  if (typeof value !== 'object' || value === null) return false;
  const type = (value as { type?: unknown }).type;
  return typeof type === 'string' && KNOWN_EVENT_TYPES.has(type);
}
