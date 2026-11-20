import type { ReactNode } from 'react';
import type { ReportKeyFigure } from '../../protocol/generated.js';
import { displayWidth } from '../../render/format.js';
import type { Piece } from '../../render/markdown.js';
import { chipPiece } from './CitationChip.js';
import { INDENT, PieceLines, Section, alignLeft, alignRight, piece, spaces } from './layout.js';

export interface KeyFiguresProps {
  figures: readonly ReportKeyFigure[];
  width: number;
  /** Wide layouts add the `as of` column; narrow ones keep label, value and source. */
  wide: boolean;
}

const GAP = 2;
const MAX_LABEL = 30;

/** Table of formatted values. The value column is right-aligned; the source is a chip at the right edge. */
export function KeyFigures({ figures, width, wide }: KeyFiguresProps): ReactNode {
  if (figures.length === 0) return null;
  const valueW = Math.max(5, ...figures.map((f) => displayWidth(f.value_text)));
  const asOfW = wide ? Math.max(6, ...figures.map((f) => displayWidth(f.as_of_text ?? ''))) : 0;
  const srcW = Math.max(6, ...figures.map((f) => (f.source_ref == null ? 0 : displayWidth(`[${f.source_ref}]`))));
  const fixed = INDENT + GAP + valueW + (wide ? GAP + asOfW : 0) + GAP + srcW;
  const labelW = Math.max(8, Math.min(MAX_LABEL, width - fixed));

  const header: Piece[] = [
    piece(alignRight('value', valueW), 'dim'),
    ...(wide ? [spaces(GAP), piece(alignLeft('as of', asOfW), 'dim')] : []),
    spaces(GAP),
    piece(alignRight('source', srcW), 'dim'),
  ];
  const rows = figures.map((f): Piece[] => [
    spaces(INDENT),
    piece(alignLeft(f.label, labelW)),
    spaces(GAP),
    piece(alignRight(f.value_text, valueW)),
    ...(wide ? [spaces(GAP), piece(alignLeft(f.as_of_text ?? '', asOfW), 'faint')] : []),
    spaces(GAP),
    ...(f.source_ref == null
      ? [spaces(srcW)]
      : [spaces(srcW - displayWidth(`[${f.source_ref}]`)), chipPiece(f.source_ref)]),
  ]);
  const tableW = INDENT + labelW + GAP + valueW + (wide ? GAP + asOfW : 0) + GAP + srcW;
  return (
    <Section title="Key figures" width={tableW} note={header}>
      <PieceLines lines={rows} width={tableW} />
    </Section>
  );
}
