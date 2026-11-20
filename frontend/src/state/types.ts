/**
 * Presentation state: a 1:1 mirror of `backend/finai/state.py`.
 *
 * Field names are camelCase in TS. `toGoldenJSON` maps them to the snake_case
 * keys, sorted, that Python emits with `sort_keys=True`, so the goldens can be
 * compared exactly.
 */

/** Every `PresentationPhase` value from state.py, in declaration order. */
export const PHASES = [
  'idle',
  'starting',
  'planning',
  'researching',
  'analysing',
  'validating',
  'generating',
  'cancelling',
  'waiting_for_approval',
  'waiting_for_clarification',
  'complete',
  'failed',
  'cancelled',
] as const;

export type Phase = (typeof PHASES)[number];

/** Phases the UI sets itself (not driven by events). */
export type UiSetPhase = 'starting' | 'cancelling' | 'cancelled';

export type ActivityStatus = 'running' | 'completed' | 'failed';

export interface ActivityState {
  readonly label: string;
  readonly status: ActivityStatus;
  readonly detail: string | null;
}

/** A source dict as received in `sources.updated` (e.g. `{name, url}`). */
export type SourceRecord = Readonly<Record<string, string>>;

export interface PresentationState {
  readonly phase: Phase;
  readonly runId: string | null;
  readonly query: string | null;
  readonly responseText: string;
  readonly responseDeltaCount: number;
  readonly terminalStatus: string | null;
  readonly error: string | null;
  readonly latestSequence: number;
  readonly lastEventType: string | null;
  readonly currentOperation: string | null;
  readonly activeTools: readonly string[];
  readonly activities: Readonly<Record<string, ActivityState>>;
  readonly sources: readonly SourceRecord[];
  /**
   * Internal, not part of the golden shape: the dedupe key `[url, display label]`
   * for each entry of `sources`, parallel to it. The label comes from
   * `display.sources`, so the reducer never re-derives source wording.
   */
  readonly sourceKeys: readonly string[];
  /** Event sequences already applied (duplicates are ignored). */
  readonly seenSequences: ReadonlySet<number>;
}

export function initialState(): PresentationState {
  return {
    phase: 'idle',
    runId: null,
    query: null,
    responseText: '',
    responseDeltaCount: 0,
    terminalStatus: null,
    error: null,
    latestSequence: 0,
    lastEventType: null,
    currentOperation: null,
    activeTools: [],
    activities: {},
    sources: [],
    sourceKeys: [],
    seenSequences: new Set<number>(),
  };
}

export interface GoldenActivity {
  detail: string | null;
  label: string;
  status: ActivityStatus;
}

/** Exact shape of the Python `PresentationState` as serialized in the goldens. */
export interface GoldenState {
  active_tools: string[];
  activities: Record<string, GoldenActivity>;
  current_operation: string | null;
  error: string | null;
  last_event_type: string | null;
  latest_sequence: number;
  phase: Phase;
  query: string | null;
  response_delta_count: number;
  response_text: string;
  run_id: string | null;
  seen_sequences: number[];
  sources: Record<string, string>[];
  terminal_status: string | null;
}

function sortedRecord(value: Readonly<Record<string, string>>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of Object.keys(value).sort()) {
    out[key] = value[key] ?? '';
  }
  return out;
}

/**
 * Serialize like Python `json.dumps(sort_keys=True)` of the state: UUID → str,
 * frozenset → sorted list, enum → value, ActivityState → dict. Keys are
 * inserted in sorted order so `JSON.stringify` matches Python's output.
 */
export function toGoldenJSON(state: PresentationState): GoldenState {
  const activities: Record<string, GoldenActivity> = {};
  for (const key of Object.keys(state.activities).sort()) {
    const activity = state.activities[key];
    if (!activity) continue;
    activities[key] = {
      detail: activity.detail,
      label: activity.label,
      status: activity.status,
    };
  }
  return {
    active_tools: [...state.activeTools],
    activities,
    current_operation: state.currentOperation,
    error: state.error,
    last_event_type: state.lastEventType,
    latest_sequence: state.latestSequence,
    phase: state.phase,
    query: state.query,
    response_delta_count: state.responseDeltaCount,
    response_text: state.responseText,
    run_id: state.runId,
    seen_sequences: [...state.seenSequences].sort((a, b) => a - b),
    sources: state.sources.map(sortedRecord),
    terminal_status: state.terminalStatus,
  };
}
