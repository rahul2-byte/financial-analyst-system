import type { ReactNode } from 'react';
import type { ReportRisk } from '../../protocol/generated.js';
import { inlineSegments } from '../../render/markdown.js';
import { glyphs } from '../../render/theme.js';
import { chipPieces } from './CitationChip.js';
import { INDENT, PieceLines, Section, piece, spaces, wrapRows } from './layout.js';

export interface RisksProps {
  risks: readonly ReportRisk[];
  width: number;
}

/** Risks and the contrarian view: a warn glyph, then the text and its source chips. */
export function Risks({ risks, width }: RisksProps): ReactNode {
  if (risks.length === 0) return null;
  const lines = risks.flatMap((r) => {
    const refs = r.source_refs ?? [];
    const segments = [
      ...inlineSegments(r.text),
      ...(refs.length > 0
        ? [{ text: ' ', style: {} }, ...chipPieces(refs).map((p) => ({ text: p.text, style: p.style }))]
        : []),
    ];
    return wrapRows(segments, width, [spaces(INDENT), piece(`${glyphs.warn} `, 'warn')], [spaces(INDENT + 2)]);
  });
  return (
    <Section title="Risks and contrarian view" width={width}>
      <PieceLines lines={lines} width={width} />
    </Section>
  );
}
