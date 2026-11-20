/**
 * Pure port of `reduce_event` in `backend/finai/state.py`.
 *
 * Every piece of user-facing wording that state.py gets from a `display.py`
 * helper (friendly errors, provider notices, provider detail strings, source
 * labels, review note) is read from the `display` object sent with the event.
 * Nothing here re-derives that wording.
 */
import type { Display, ResearchEvent } from '../protocol/generated.js';
import type {
  ActivityState,
  ActivityStatus,
  Phase,
  PresentationState,
  SourceRecord,
  UiSetPhase,
} from './types.js';

/** Fallback only; the bridge sends `display.review_note` for this case. */
export const REVIEW_UNAVAILABLE_NOTE =
  'Note: independent answer review was unavailable; numbers were checked against tool evidence.';

/** Mirrors `_short_detail`: truncate to `limit` code points with an ellipsis. */
export function shortDetail(detail: string | null | undefined, limit = 120): string | null {
  if (detail === null || detail === undefined) return null;
  const chars = Array.from(detail);
  return chars.length > limit ? `${chars.slice(0, limit - 1).join('')}…` : detail;
}

/** Mirrors `_phase_for_stage`. Unknown stages default to researching. */
export function phaseForStage(stage: string): Phase {
  switch (stage.toLowerCase()) {
    case 'planning':
      return 'planning';
    case 'research':
      return 'researching';
    case 'analysis':
      return 'analysing';
    case 'validation':
      return 'validating';
    case 'generation':
      return 'generating';
    default:
      return 'researching';
  }
}

/** Phase set by the UI itself (`STARTING`, `CANCELLING`, `CANCELLED` in the Python app). */
export function localPhase(state: PresentationState, phase: UiSetPhase): PresentationState {
  return state.phase === phase ? state : { ...state, phase };
}

function withActivities(
  activities: Readonly<Record<string, ActivityState>>,
  key: string,
  activity: ActivityState,
): Readonly<Record<string, ActivityState>> {
  return { ...activities, [key]: activity };
}

function activity(label: string, status: ActivityStatus, detail: string | null): ActivityState {
  return { label, status, detail };
}

/** Apply one event. A sequence already seen is ignored and returns `state` itself. */
export function reduceEvent(
  state: PresentationState,
  event: ResearchEvent,
  display: Display | null,
): PresentationState {
  const sequence = event.meta.sequence;
  if (state.seenSequences.has(sequence)) return state;
  const next: PresentationState = {
    ...state,
    latestSequence: Math.max(sequence, state.latestSequence),
    lastEventType: event.type,
    seenSequences: new Set([...state.seenSequences, sequence]),
  };
  return apply(next, event, display);
}

function apply(state: PresentationState, event: ResearchEvent, display: Display | null): PresentationState {
  switch (event.type) {
    case 'run.started':
      return { ...state, phase: 'starting', runId: event.meta.run_id, query: event.query };

    case 'stage.started': {
      let activities = state.activities;
      const running = state.currentOperation;
      if (running) {
        const next: Record<string, ActivityState> = {};
        for (const [key, item] of Object.entries(activities)) {
          next[key] =
            item.label === running && item.status === 'running' ? { ...item, status: 'completed' } : item;
        }
        activities = next;
      }
      activities = withActivities(activities, event.stage, activity(event.label, 'running', null));
      return {
        ...state,
        phase: phaseForStage(event.stage),
        currentOperation: event.label,
        activities,
      };
    }

    case 'model.request.started':
      return {
        ...state,
        phase: 'generating',
        currentOperation: 'Contacting model',
        activities: withActivities(state.activities, 'model', activity('Contacting model', 'running', null)),
      };

    case 'provider.attempt.started':
      return {
        ...state,
        phase: 'generating',
        currentOperation: 'Contacting OpenRouter',
        activities: withActivities(
          state.activities,
          'provider',
          activity('Contacting OpenRouter', 'running', `attempt ${event.attempt}`),
        ),
      };

    case 'provider.retrying':
      return {
        ...state,
        phase: 'generating',
        currentOperation: 'Retrying OpenRouter',
        activities: withActivities(
          state.activities,
          'provider',
          activity('Retrying OpenRouter', 'running', display?.detail ?? null),
        ),
      };

    case 'provider.stream.started':
      return {
        ...state,
        phase: 'generating',
        currentOperation: 'Streaming response',
        activities: withActivities(
          state.activities,
          'provider',
          activity('Streaming response', 'running', display?.detail ?? null),
        ),
      };

    case 'provider.completed':
    case 'provider.failed': {
      let providerActivity: ActivityState;
      if (event.type === 'provider.completed') {
        providerActivity = activity('OpenRouter', 'completed', display?.detail ?? null);
      } else {
        const notice = display?.notice ?? null;
        providerActivity = notice
          ? activity(notice, 'failed', null)
          : activity('OpenRouter', 'failed', display?.friendly ?? event.message);
      }
      return {
        ...state,
        activities: withActivities(state.activities, 'provider', providerActivity),
        currentOperation: null,
      };
    }

    case 'tool.progress': {
      const key = `tool:${event.tool_id}`;
      const current = state.activities[key];
      return {
        ...state,
        activities: current
          ? withActivities(state.activities, key, { ...current, detail: event.message })
          : state.activities,
        currentOperation: event.message,
      };
    }

    case 'stage.completed':
    case 'stage.failed': {
      const current = state.activities[event.stage];
      if (!current) return state;
      const failed = event.type === 'stage.failed';
      const detail = event.type === 'stage.failed' ? event.message : (event.detail ?? null);
      return {
        ...state,
        activities: withActivities(state.activities, event.stage, {
          ...current,
          status: failed ? 'failed' : 'completed',
          detail,
        }),
        currentOperation: state.currentOperation === current.label ? null : state.currentOperation,
      };
    }

    case 'tool.started': {
      const toolKey = event.tool_id || event.tool;
      return {
        ...state,
        phase: 'researching',
        currentOperation: event.tool,
        activeTools: [...state.activeTools, toolKey],
        activities: withActivities(
          state.activities,
          `tool:${toolKey}`,
          activity(event.tool, 'running', event.detail ?? null),
        ),
      };
    }

    case 'tool.completed':
    case 'tool.failed': {
      const toolKey = event.tool_id || event.tool;
      const key = `tool:${toolKey}`;
      let current = state.activities[key];
      if (!current && event.type === 'tool.failed') {
        current = activity(event.tool, 'running', null);
      }
      let activities = state.activities;
      if (current) {
        const failed = event.type === 'tool.failed';
        const detail = event.type === 'tool.failed'
          ? (display?.friendly ?? event.message)
          : (event.detail ?? null);
        activities = withActivities(activities, key, {
          label: current.label,
          status: failed ? 'failed' : 'completed',
          detail: shortDetail(detail),
        });
      }
      return {
        ...state,
        activities,
        activeTools: state.activeTools.filter((tool) => tool !== toolKey),
        currentOperation: state.currentOperation === event.tool ? null : state.currentOperation,
      };
    }

    case 'response.delta':
      return {
        ...state,
        phase: 'generating',
        responseText: state.responseText + event.text,
        responseDeltaCount: state.responseDeltaCount + 1,
      };

    case 'sources.updated': {
      const labels = display?.sources;
      if (!labels || labels.length !== event.sources.length) {
        throw new Error('sources.updated: display.sources must align with event.sources');
      }
      const sources: SourceRecord[] = [...state.sources];
      const sourceKeys: string[] = [...state.sourceKeys];
      const seen = new Set(sourceKeys);
      event.sources.forEach((source, index) => {
        const label = labels[index]?.label ?? '';
        const key = JSON.stringify([source.url ?? '', label]);
        if (seen.has(key)) return;
        seen.add(key);
        sources.push({ ...source });
        sourceKeys.push(key);
      });
      return { ...state, sources, sourceKeys };
    }

    case 'approval.requested':
      return { ...state, phase: 'waiting_for_approval' };

    case 'clarification.requested':
      return { ...state, phase: 'waiting_for_clarification' };

    case 'approval.resolved':
      return { ...state, phase: 'researching' };

    case 'run.completed': {
      const activities: Record<string, ActivityState> = {};
      for (const [key, item] of Object.entries(state.activities)) {
        activities[key] = item.status === 'running' ? activity(item.label, 'completed', item.detail) : item;
      }
      if (display?.review_unavailable === true) {
        activities.output_review = activity(
          display.review_note ?? REVIEW_UNAVAILABLE_NOTE,
          'completed',
          null,
        );
      }
      return {
        ...state,
        phase: 'complete',
        terminalStatus: event.terminal_status,
        currentOperation: null,
        activeTools: [],
        activities,
      };
    }

    case 'run.failed':
      return {
        ...state,
        phase: 'failed',
        error: event.message,
        terminalStatus: 'failed',
        currentOperation: null,
        activeTools: [],
      };

    case 'run.cancelled':
      return {
        ...state,
        phase: 'cancelled',
        terminalStatus: 'cancelled',
        currentOperation: null,
        activeTools: [],
      };

    default:
      // check.stage, context.compacted, skill.selected, route.decision.made and
      // model.response.completed have no branch in state.py; sequence still recorded.
      return state;
  }
}
