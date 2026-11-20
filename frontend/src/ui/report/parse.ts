/**
 * Runtime check for `run.finished.report`. The bridge is trusted to send the schema, but
 * a report that fails these checks must never half-render: `parseReport` returns null and
 * the caller shows the Markdown answer instead (fail closed). Every string is sanitised.
 */
import type {
  ReportDriver,
  ReportEvidence,
  ReportInstrument,
  ReportKeyFigure,
  ReportQuote,
  ReportRisk,
  ReportSignal,
  ReportSource,
  ReportSourceStatus,
  ReportSparkline,
  ReportView,
} from '../../protocol/generated.js';
import { sanitizeTerminalText } from '../../render/sanitize.js';

type Obj = Record<string, unknown>;

class Invalid extends Error {}

const fail = (what: string): never => {
  throw new Invalid(what);
};

const isObj = (value: unknown): value is Obj => typeof value === 'object' && value !== null && !Array.isArray(value);

function obj(value: unknown, what: string): Obj {
  return isObj(value) ? value : fail(what);
}

function str(value: unknown, what: string): string {
  return typeof value === 'string' ? sanitizeTerminalText(value) : fail(what);
}

function optStr(value: unknown, what: string): string | null {
  return value === undefined || value === null ? null : str(value, what);
}

function list<T>(value: unknown, what: string, each: (item: unknown, index: number) => T): T[] {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value.map(each) : fail(what);
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], what: string): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : fail(what);
}

function int(value: unknown, what: string): number {
  return typeof value === 'number' && Number.isInteger(value) ? value : fail(what);
}

const refs = (value: unknown, what: string): number[] => list(value, what, (v) => int(v, what));

function sourceStatus(value: unknown): ReportSourceStatus {
  const o = obj(value, 'evidence source');
  return {
    name: str(o.name, 'evidence source name'),
    reason: optStr(o.reason, 'evidence source reason'),
    status: oneOf(o.status, ['available', 'degraded', 'unavailable'] as const, 'evidence source status'),
  };
}

function evidence(value: unknown): ReportEvidence {
  const o = obj(value, 'evidence');
  return {
    status: oneOf(o.status, ['complete', 'limited'] as const, 'evidence status'),
    observed_through_text: optStr(o.observed_through_text, 'observed_through_text'),
    sources: list(o.sources, 'evidence sources', sourceStatus),
  };
}

function instrument(value: unknown): ReportInstrument | null {
  if (value === undefined || value === null) return null;
  const o = obj(value, 'instrument');
  return {
    symbol: str(o.symbol, 'instrument symbol'),
    name: optStr(o.name, 'instrument name'),
    exchange: optStr(o.exchange, 'instrument exchange'),
  };
}

function quote(value: unknown): ReportQuote | null {
  if (value === undefined || value === null) return null;
  const o = obj(value, 'quote');
  return {
    price_text: str(o.price_text, 'price_text'),
    change_text: optStr(o.change_text, 'change_text'),
    as_of_text: optStr(o.as_of_text, 'quote as_of_text'),
    direction:
      o.direction === undefined || o.direction === null
        ? null
        : oneOf(o.direction, ['up', 'down', 'flat'] as const, 'quote direction'),
  };
}

/** A sparkline that does not check out is left out; the rest of the report still shows. */
function sparkline(value: unknown): ReportSparkline | null {
  if (value === undefined || value === null) return null;
  try {
    const o = obj(value, 'sparkline');
    const points = Array.isArray(o.points) ? o.points : fail('sparkline points');
    if (points.length < 2 || points.length > 48) return fail('sparkline length');
    const numbers = points.map((p) => (typeof p === 'number' && p >= 0 && p <= 1 ? p : fail('sparkline point')));
    return {
      points: numbers as ReportSparkline['points'],
      period_text: str(o.period_text, 'period_text'),
      low_text: str(o.low_text, 'low_text'),
      high_text: str(o.high_text, 'high_text'),
    };
  } catch (error) {
    if (error instanceof Invalid) return null;
    throw error;
  }
}

function keyFigure(value: unknown): ReportKeyFigure {
  const o = obj(value, 'key figure');
  return {
    label: str(o.label, 'key figure label'),
    value_text: str(o.value_text, 'key figure value'),
    as_of_text: optStr(o.as_of_text, 'key figure as_of'),
    source_ref: o.source_ref === undefined || o.source_ref === null ? null : int(o.source_ref, 'key figure ref'),
  };
}

function signal(value: unknown): ReportSignal {
  const o = obj(value, 'signal');
  const strength = o.strength;
  if (strength !== undefined && strength !== null && !(typeof strength === 'number' && strength >= 0 && strength <= 1)) {
    fail('signal strength');
  }
  return {
    name: str(o.name, 'signal name'),
    value_text: str(o.value_text, 'signal value'),
    direction: oneOf(o.direction, ['bullish', 'bearish', 'neutral', 'unavailable'] as const, 'signal direction'),
    state_text: optStr(o.state_text, 'signal state'),
    percentile_text: optStr(o.percentile_text, 'signal percentile'),
    strength: typeof strength === 'number' ? strength : null,
  };
}

function driver(value: unknown): ReportDriver {
  const o = obj(value, 'driver');
  return {
    text: str(o.text, 'driver text'),
    importance: oneOf(o.importance, ['major', 'supporting', 'minor'] as const, 'driver importance'),
    source_refs: refs(o.source_refs, 'driver refs'),
  };
}

function risk(value: unknown): ReportRisk {
  const o = obj(value, 'risk');
  return { text: str(o.text, 'risk text'), source_refs: refs(o.source_refs, 'risk refs') };
}

function source(value: unknown): ReportSource {
  const o = obj(value, 'source');
  return {
    ref: int(o.ref, 'source ref'),
    label: str(o.label, 'source label'),
    url: str(o.url, 'source url'),
    host: optStr(o.host, 'source host'),
    retrieved_text: optStr(o.retrieved_text, 'source retrieved'),
    freshness_text: optStr(o.freshness_text, 'source freshness'),
    trust: optStr(o.trust, 'source trust'),
  };
}

/** The sanitised report, or null when anything required is missing or malformed. */
export function parseReport(value: unknown): ReportView | null {
  if (value === undefined || value === null) return null;
  try {
    const o = obj(value, 'report');
    return {
      kind: oneOf(o.kind, ['report', 'lookup'] as const, 'kind'),
      instrument: instrument(o.instrument),
      quote: quote(o.quote),
      sparkline: sparkline(o.sparkline),
      evidence: evidence(o.evidence),
      stance_text: optStr(o.stance_text, 'stance_text'),
      summary: str(o.summary, 'summary'),
      key_figures: list(o.key_figures, 'key_figures', keyFigure),
      signals: list(o.signals, 'signals', signal),
      drivers: list(o.drivers, 'drivers', driver),
      risks: list(o.risks, 'risks', risk),
      final_view: optStr(o.final_view, 'final_view'),
      detailed_analysis: optStr(o.detailed_analysis, 'detailed_analysis'),
      limitations: list(o.limitations, 'limitations', (v) => str(v, 'limitation')),
      sources: list(o.sources, 'sources', source),
      disclaimer: str(o.disclaimer, 'disclaimer'),
    };
  } catch (error) {
    if (error instanceof Invalid) return null;
    throw error;
  }
}
