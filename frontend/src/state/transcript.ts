/**
 * Transcript model: what gets committed to the terminal scrollback (Ink `<Static>`)
 * and in which order.
 *
 * Commit order per run: user → activity-trail → answer-chunk* → sources →
 * clarification | notice → run-footer. The activity trail is committed (collapsed)
 * when the first answer chunk commits, or when the run finishes.
 */
import type { DisplayCandidate, DisplaySource, ReportView } from '../protocol/generated.js';
import { humanLabel, isRawToolId } from '../render/format.js';
import type { ActivityState, ActivityStatus, PresentationState } from './types.js';

/** One tool line of the expanded activity trail. Labels are already human text. */
export interface TrailRow {
  readonly label: string;
  readonly status: ActivityStatus;
  readonly detail: string;
}

export type TranscriptItem =
  | { kind: 'header'; id: string; title: string; mode: string; model: string }
  | { kind: 'user'; id: string; runId: string; text: string }
  | {
      kind: 'activity-trail';
      id: string;
      runId: string;
      collapsed: boolean;
      toolCount: number;
      failedNouns: readonly string[];
      /** Tool lines, shown when `collapsed` is false (Ctrl+O). */
      rows: readonly TrailRow[];
    }
  | { kind: 'answer-chunk'; id: string; runId: string; index: number; text: string }
  | { kind: 'sources'; id: string; runId: string; sources: readonly DisplaySource[] }
  | { kind: 'report'; id: string; runId: string; report: ReportView }
  | {
      kind: 'clarification';
      id: string;
      runId: string;
      candidates: readonly DisplayCandidate[];
      lines: readonly string[];
    }
  | { kind: 'notice'; id: string; runId: string; tone: 'warn' | 'loss' | 'dim'; text: string }
  | {
      kind: 'run-footer';
      id: string;
      runId: string;
      status: string;
      elapsedMs: number | null;
      toolCount: number;
      sourceCount: number;
      partial: boolean;
      /** Lower-case names of evidence that could not be fetched, e.g. `news`. */
      unavailable: readonly string[];
      /** Short failure reason for `failed` runs. */
      reason: string | null;
    }
  | { kind: 'command-output'; id: string; lines: readonly string[] };

// ---------------------------------------------------------------------------
// Stable-prefix splitting
// ---------------------------------------------------------------------------

export interface StableSplit {
  /** Complete blocks. Each string is an exact slice of the input, blank-line separators included. */
  stable: string[];
  /** Everything after the last stable block; still live. `stable.join('') + tail === text`. */
  tail: string;
}

export interface SplitOptions {
  /** The run has ended, so an unterminated last line counts as complete. */
  final?: boolean;
}

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})[ \t]*$/;
// Lines that can belong to a list, an indented block or a table. A list or table may
// continue after a blank line, so a cut between two such blocks is not safe.
const LIST_OR_TABLE = /^(?:[ \t]*(?:[-*+]|\d+[.)])(?:[ \t]|$)|[ \t]{2,}\S|\t|[ \t]*\||[ \t]*:?-{3,}:?[ \t]*\|)/;

interface Boundary {
  /** Offset where the next block starts (the first non-blank line after a blank run). */
  end: number;
  /** The block that ends here contains list, table or indented lines. */
  previousListish: boolean;
  nextText: string;
  nextComplete: boolean;
}

/**
 * Split accumulated Markdown into blocks that will not change once emitted, plus a
 * live tail.
 *
 * A cut is a blank-line run followed by a non-blank line, with no fenced code block
 * open. A cut is safe when the next line is complete and either it is a plain line
 * (which ends any list or table before it) or the block before it has no list or
 * table lines. Cuts before a list item or an indented line that follows a list or
 * table are held back, because that list may still continue.
 */
export function splitStableMarkdown(text: string, options: SplitOptions = {}): StableSplit {
  const final = options.final === true;
  const boundaries: Boundary[] = [];
  let fence: { char: string; length: number } | null = null;
  let hasContent = false;
  let sawBlank = false;
  let listish = false;
  let offset = 0;

  while (offset < text.length) {
    const newline = text.indexOf('\n', offset);
    const complete = newline !== -1 || final;
    const lineEnd = newline !== -1 ? newline + 1 : text.length;
    const content = (newline !== -1 ? text.slice(offset, newline) : text.slice(offset)).replace(/\r$/, '');
    const blank = content.trim() === '';

    if (fence === null && !blank && hasContent && sawBlank) {
      boundaries.push({ end: offset, previousListish: listish, nextText: content, nextComplete: complete });
      hasContent = false;
      sawBlank = false;
      listish = false;
    }

    if (fence !== null) {
      hasContent = true;
      const close = FENCE_CLOSE.exec(content);
      if (close && close[1]?.[0] === fence.char && close[1].length >= fence.length) {
        fence = null;
        // A closed fence ends its block even without a blank line after it.
        sawBlank = true;
      }
    } else if (blank) {
      if (hasContent) sawBlank = true;
    } else {
      hasContent = true;
      const open = FENCE_OPEN.exec(content);
      if (open?.[1]) fence = { char: open[1][0] ?? '`', length: open[1].length };
      if (LIST_OR_TABLE.test(content)) listish = true;
    }
    offset = lineEnd;
  }

  const cuts = boundaries
    .filter((b) => !b.previousListish || (b.nextComplete && !LIST_OR_TABLE.test(b.nextText)))
    .map((b) => b.end);
  const stable: string[] = [];
  let start = 0;
  for (const cut of cuts) {
    stable.push(text.slice(start, cut));
    start = cut;
  }
  return { stable, tail: text.slice(start) };
}

// ---------------------------------------------------------------------------
// Commit helpers
// ---------------------------------------------------------------------------

export interface StreamDraft {
  readonly runId: string;
  /** Stable blocks already committed, in order. Never changes once emitted. */
  readonly emitted: readonly string[];
  readonly trailCommitted: boolean;
}

export interface CommitResult {
  draft: StreamDraft;
  items: TranscriptItem[];
}

export function startDraft(runId: string): StreamDraft {
  return { runId, emitted: [], trailCommitted: false };
}

function assertPrefix(draft: StreamDraft, stable: readonly string[]): void {
  draft.emitted.forEach((block, index) => {
    if (stable[index] !== block) {
      throw new Error(`stable answer block ${index} changed after it was committed`);
    }
  });
}

function chunkItem(runId: string, index: number, text: string): TranscriptItem {
  return { kind: 'answer-chunk', id: `${runId}:chunk:${index}`, runId, index, text };
}

/**
 * Commit the stable blocks that are new since the last call. The first commit
 * also commits the activity trail, built by `trail()` from the state at that time.
 */
export function commitStreamingText(
  draft: StreamDraft,
  text: string,
  trail: () => TranscriptItem,
): CommitResult {
  const { stable } = splitStableMarkdown(text);
  assertPrefix(draft, stable);
  const fresh = stable.slice(draft.emitted.length);
  if (fresh.length === 0) return { draft, items: [] };

  const items: TranscriptItem[] = [];
  if (!draft.trailCommitted) items.push(trail());
  fresh.forEach((block, offset) => items.push(chunkItem(draft.runId, draft.emitted.length + offset, block)));
  return {
    draft: { runId: draft.runId, emitted: stable, trailCommitted: true },
    items,
  };
}

export interface FinishParts {
  /** Used only if the trail was not committed during streaming. */
  trail: () => TranscriptItem;
  /** Clarification or notice items, already in order. */
  closing: readonly TranscriptItem[];
  sources: TranscriptItem | null;
  footer: TranscriptItem;
}

/**
 * Commit everything left at `run.finished`: the trail if still pending, the remaining
 * stable blocks, the live tail, then sources, closing items and the footer.
 */
export function commitFinal(draft: StreamDraft, text: string, parts: FinishParts): CommitResult {
  const { stable, tail } = splitStableMarkdown(text, { final: true });
  assertPrefix(draft, stable);
  const items: TranscriptItem[] = [];
  if (!draft.trailCommitted) items.push(parts.trail());
  stable.slice(draft.emitted.length).forEach((block, offset) => {
    items.push(chunkItem(draft.runId, draft.emitted.length + offset, block));
  });
  if (tail.trim() !== '') items.push(chunkItem(draft.runId, stable.length, tail));
  if (parts.sources) items.push(parts.sources);
  items.push(...parts.closing);
  items.push(parts.footer);
  return {
    draft: { runId: draft.runId, emitted: stable, trailCommitted: true },
    items,
  };
}

export function userItem(runId: string, text: string): TranscriptItem {
  return { kind: 'user', id: `${runId}:user`, runId, text };
}

/** Tool lines for the expanded trail. A tool without a human label is left out; raw ids never print. */
export function trailRows(activities: Readonly<Record<string, ActivityState>>): TrailRow[] {
  return Object.entries(activities).flatMap(([key, activity]) => {
    if (!key.startsWith('tool:')) return [];
    const label = humanLabel(activity.label);
    if (label === null) return [];
    const detail = activity.detail !== null && !isRawToolId(activity.detail) ? activity.detail.trim() : '';
    return [{ label, status: activity.status, detail }];
  });
}

/** Activity trail built from the reducer state. Counts `tool:` activities only. */
export function activityTrailItem(
  runId: string,
  state: PresentationState,
  failedNouns: readonly string[],
  collapsed: boolean,
  activities: Readonly<Record<string, ActivityState>> = state.activities,
): TranscriptItem {
  const toolCount = Object.keys(state.activities).filter((key) => key.startsWith('tool:')).length;
  return {
    kind: 'activity-trail',
    id: `${runId}:trail`,
    runId,
    collapsed,
    toolCount,
    failedNouns,
    rows: trailRows(activities),
  };
}

// ---------------------------------------------------------------------------
// Failure wording
// ---------------------------------------------------------------------------

const RAW_ID = /\b[a-z_]+:[a-z0-9_]+\b/g;

/** One plain sentence: raw tool ids and control noise removed. */
export function plainSentence(text: string): string {
  const cleaned = text
    .replace(RAW_ID, (id) => humanLabel(id) ?? 'a data source')
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned.replace(/[.\s]+$/, '');
}

const NEXT_STEPS: readonly { test: RegExp; reason: string; next: string }[] = [
  { test: /quota|credit|insufficient|\b402\b/i, reason: 'The model provider quota is used up', next: 'Add credits, then /retry' },
  { test: /auth|api key|unauthori[sz]ed|\b40[13]\b/i, reason: 'The model provider rejected the API key', next: 'Check OPENROUTER_API_KEY, then /retry' },
  { test: /rate.?limit|too many|\b429\b/i, reason: 'The model provider is rate limiting requests', next: 'Wait a minute, then /retry' },
  { test: /time.?out|timed out|server error|unavailable|\b5\d\d\b/i, reason: 'The model provider did not respond', next: 'Try /retry' },
];

export interface Failure {
  /** Short reason for the footer, no trailing full stop. */
  readonly reason: string;
  /** Notice line: the reason plus the next step. */
  readonly notice: string;
}

/** Friendly reason and next step for a failed run. `raw` is every message the run produced. */
export function describeFailure(raw: readonly (string | null | undefined)[]): Failure {
  const parts = raw.map((value) => plainSentence(value ?? '')).filter((value) => value !== '');
  const joined = parts.join(' ');
  for (const step of NEXT_STEPS) {
    if (step.test.test(joined)) return { reason: step.reason, notice: `${step.reason}. ${step.next}.` };
  }
  const reason = parts[0] ?? 'The run did not finish';
  return { reason, notice: `${reason}. Try /retry.` };
}

export function sourcesItem(runId: string, sources: readonly DisplaySource[]): TranscriptItem | null {
  return sources.length === 0 ? null : { kind: 'sources', id: `${runId}:sources`, runId, sources };
}

export function runFooterItem(
  runId: string,
  details: {
    status: string;
    elapsedMs: number | null;
    toolCount: number;
    sourceCount: number;
    partial: boolean;
    unavailable: readonly string[];
    reason: string | null;
  },
): TranscriptItem {
  return { kind: 'run-footer', id: `${runId}:footer`, runId, ...details };
}
