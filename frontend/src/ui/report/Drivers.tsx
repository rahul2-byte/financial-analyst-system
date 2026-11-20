import type { ReactNode } from 'react';
import type { ReportDriver } from '../../protocol/generated.js';
import { inlineSegments } from '../../render/markdown.js';
import type { Token } from '../../render/theme.js';
import { chipPieces } from './CitationChip.js';
import { INDENT, PieceLines, Section, piece, spaces, tint, wrapRows } from './layout.js';

export interface DriversProps {
  drivers: readonly ReportDriver[];
  width: number;
}

const MARKER: Record<ReportDriver['importance'], { glyph: string; tone?: Token }> = {
  major: { glyph: '▸' },
  supporting: { glyph: '▸', tone: 'dim' },
  minor: { glyph: '·', tone: 'dim' },
};

/** Key drivers, most important first as Python ordered them. Minor drivers read dim. */
export function Drivers({ drivers, width }: DriversProps): ReactNode {
  if (drivers.length === 0) return null;
  const lines = drivers.flatMap((d) => {
    const m = MARKER[d.importance];
    const refs = d.source_refs ?? [];
    const segments = [
      ...tint(inlineSegments(d.text), d.importance === 'minor' ? 'dim' : undefined),
      ...(refs.length > 0
        ? [{ text: ' ', style: {} }, ...chipPieces(refs).map((p) => ({ text: p.text, style: p.style }))]
        : []),
    ];
    return wrapRows(segments, width, [spaces(INDENT), piece(`${m.glyph} `, m.tone)], [spaces(INDENT + 2)]);
  });
  return (
    <Section title="Key drivers" width={width}>
      <PieceLines lines={lines} width={width} />
    </Section>
  );
}
