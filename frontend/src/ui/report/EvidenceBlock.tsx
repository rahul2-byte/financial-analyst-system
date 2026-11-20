import type { ReactNode } from 'react';
import type { ReportEvidence } from '../../protocol/generated.js';
import { inlineSegments } from '../../render/markdown.js';
import type { Piece } from '../../render/markdown.js';
import { glyphs } from '../../render/theme.js';
import { INDENT, PieceLines, Section, piece, spaces, wrapRows } from './layout.js';

export interface EvidenceBlockProps {
  evidence: ReportEvidence;
  limitations: readonly string[];
  width: number;
}

const unavailableName = (evidence: ReportEvidence): string[] =>
  (evidence.sources ?? []).filter((s) => s.status !== 'available').map((s) => s.name.toLowerCase());

/** Evidence and limitations: which sources were available, why one was not, and the data date. */
export function EvidenceBlock({ evidence, limitations, width }: EvidenceBlockProps): ReactNode {
  const sources = evidence.sources ?? [];
  const missing = unavailableName(evidence);
  // A limitation that only restates an unavailable source row would say it twice.
  const extra = limitations.filter((text) => !missing.some((name) => text.toLowerCase().startsWith(name)));
  const lines: Piece[][] = [];

  const available = sources.filter((s) => s.status === 'available');
  if (available.length > 0) {
    const segments = available.flatMap((s, i) => [
      ...(i > 0 ? [{ text: '   ', style: {} }] : []),
      { text: `${glyphs.ok} `, style: { color: piece('', 'gain').style.color } },
      { text: s.name.toLowerCase(), style: {} },
    ]);
    lines.push(...wrapRows(segments, width, [spaces(INDENT)], [spaces(INDENT)]));
  }
  for (const s of sources.filter((x) => x.status !== 'available')) {
    const mark = s.status === 'degraded' ? '◐' : glyphs.fail;
    const text = `${s.name.toLowerCase()}  ${s.status}${s.reason ? ` · ${s.reason}` : ''}`;
    lines.push(
      ...wrapRows(
        [{ text, style: {} }],
        width,
        [spaces(INDENT), piece(`${mark} `, 'warn')],
        [spaces(INDENT + 2)],
      ),
    );
  }
  for (const text of extra) {
    lines.push(
      ...wrapRows(
        inlineSegments(text).map((s) => ({ ...s, style: { ...s.style, color: piece('', 'dim').style.color } })),
        width,
        [spaces(INDENT), piece('· ', 'dim')],
        [spaces(INDENT + 2)],
      ),
    );
  }
  if (evidence.observed_through_text) {
    lines.push([spaces(INDENT), piece(`Data observed through ${evidence.observed_through_text}`, 'dim')]);
  }
  if (lines.length === 0) return null;
  return (
    <Section title="Evidence and limitations" width={width}>
      <PieceLines lines={lines} width={width} />
    </Section>
  );
}
