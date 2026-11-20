import type { ReactNode } from 'react';
import { inlineSegments } from '../../render/markdown.js';
import { INDENT, PieceLines, piece, spaces, wrapRows } from './layout.js';
import { Box } from 'ink';

export interface FinalViewProps {
  text: string;
  width: number;
}

/** The call, set apart by a ledger left bar. */
export function FinalView({ text, width }: FinalViewProps): ReactNode {
  const bar = [spaces(INDENT), piece('┃ ', 'ledger')];
  const body = wrapRows(inlineSegments(text), width, bar, bar);
  const lines = [[...bar, piece('Final view', 'ledger', { bold: true })], ...body];
  return (
    <Box flexDirection="column" width={width} marginTop={1}>
      <PieceLines lines={lines} width={width} />
    </Box>
  );
}
