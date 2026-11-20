/**
 * Small pure helpers shared by the transcript components: display-width aware
 * truncation and wrapping, seconds formatting, pluralisation, host extraction and the
 * raw-tool-id guard used by the activity views.
 */
import stringWidth from 'string-width';

export const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'] as const;

/**
 * Raw runtime ids such as `news:fe12ab`; these must never reach the screen. Wider than
 * the plain `[a-z_]+:[a-z_]+` so that ids with digits are caught too.
 */
const RAW_TOOL_ID = /\b[a-z_]+:[a-z0-9_]+\b/;

export function displayWidth(text: string): number {
  return stringWidth(text);
}

/** True when the text is, or contains, a raw tool id. */
export function isRawToolId(text: string): boolean {
  return RAW_TOOL_ID.test(text);
}

/** A label fit for display, or null when it is empty or only a raw id. */
export function humanLabel(text: string | null | undefined): string | null {
  if (text === null || text === undefined) return null;
  const trimmed = text.trim();
  if (trimmed === '' || isRawToolId(trimmed)) return null;
  return trimmed;
}

/** `12.4s` under a minute, `1m 05.2s` from a minute on. */
export function formatSeconds(ms: number): string {
  const seconds = Math.max(0, ms) / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds - minutes * 60).toFixed(1).padStart(4, '0');
  return `${minutes}m ${rest}s`;
}

/** Whole seconds for the live spinner: `12s`, `1m 05s`. */
export function formatElapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  if (whole < 60) return `${whole}s`;
  const minutes = Math.floor(whole / 60);
  return `${minutes}m ${String(whole - minutes * 60).padStart(2, '0')}s`;
}

export function pluralize(count: number, singular: string, plural: string = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

/** Cut text to at most `width` terminal columns, ending with `…` when cut. */
export function truncate(text: string, width: number): string {
  if (width <= 0) return '';
  if (displayWidth(text) <= width) return text;
  if (width === 1) return '…';
  let out = '';
  for (const char of Array.from(text)) {
    if (displayWidth(out + char) > width - 1) break;
    out += char;
  }
  return `${out}…`;
}

/** Pad with spaces to exactly `width` columns (never truncates). */
export function padEnd(text: string, width: number): string {
  const gap = width - displayWidth(text);
  return gap > 0 ? text + ' '.repeat(gap) : text;
}

/** Split a word that is wider than `width` into pieces that fit. */
export function hardWrap(text: string, width: number): string[] {
  const limit = Math.max(1, width);
  const lines: string[] = [];
  let current = '';
  for (const char of Array.from(text)) {
    if (current !== '' && displayWidth(current + char) > limit) {
      lines.push(current);
      current = '';
    }
    current += char;
  }
  lines.push(current);
  return lines;
}

/**
 * Word-wrap prose to `width` columns. Newlines are kept; runs of whitespace inside a
 * line collapse to single spaces; words wider than `width` are hard-broken.
 */
export function wrapWords(text: string, width: number): string[] {
  const limit = Math.max(1, width);
  const out: string[] = [];
  for (const paragraph of text.split('\n')) {
    const words = paragraph.split(/\s+/).filter((word) => word !== '');
    if (words.length === 0) {
      out.push('');
      continue;
    }
    let current = '';
    for (const word of words) {
      if (displayWidth(word) > limit) {
        if (current !== '') out.push(current);
        const pieces = hardWrap(word, limit);
        const last = pieces.pop() ?? '';
        out.push(...pieces);
        current = last;
        continue;
      }
      if (current === '') {
        current = word;
      } else if (displayWidth(`${current} ${word}`) <= limit) {
        current += ` ${word}`;
      } else {
        out.push(current);
        current = word;
      }
    }
    out.push(current);
  }
  return out;
}

/** Hostname without a leading `www.`, or null when the URL does not parse. */
export function hostOf(url: string): string | null {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '');
    return host === '' ? null : host;
  } catch {
    return null;
  }
}
