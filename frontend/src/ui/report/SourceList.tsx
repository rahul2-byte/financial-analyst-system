import type { ReactNode } from 'react';
import type { ReportSource } from '../../protocol/generated.js';
import { displayWidth } from '../../render/format.js';
import type { Piece } from '../../render/markdown.js';
import { INDENT, PieceLines, Section, alignRight, piece, piecesWidth, spaces, wrapRows } from './layout.js';

export interface SourceListProps {
  sources: readonly ReportSource[];
  width: number;
}

/** Numbered sources. Long lines wrap with a hanging indent under the label, never past the terminal width. */
export function SourceList({ sources, width }: SourceListProps): ReactNode {
  if (sources.length === 0) return null;
  const numW = Math.max(...sources.map((s) => displayWidth(String(s.ref))));
  const lines = sources.flatMap((s): Piece[][] => {
    const host = s.host && !s.label.toLowerCase().includes(s.host.toLowerCase()) ? s.host : null;
    const tail = [host, s.retrieved_text, s.freshness_text].filter((v): v is string => !!v);
    const body: Piece[] = [
      piece(s.label),
      ...(tail.length > 0 ? [piece(` · ${tail.join(' · ')}`, 'faint')] : []),
    ];
    const lead = [spaces(INDENT), piece(alignRight(String(s.ref), numW), 'ledger'), spaces(2)];
    return wrapRows(body, width, lead, [spaces(piecesWidth(lead))]);
  });
  return (
    <Section title="Sources" width={width}>
      <PieceLines lines={lines} width={width} />
    </Section>
  );
}
