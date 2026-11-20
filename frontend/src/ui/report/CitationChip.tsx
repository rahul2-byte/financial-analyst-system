import { Text } from 'ink';
import { color } from '../../render/theme.js';
import type { Piece } from '../../render/markdown.js';
import { piece } from './layout.js';

/** `[1]` as a row piece: ledger on graphite, the numbers match the Sources list. */
export const chipPiece = (ref: number | string): Piece => piece(`[${ref}]`, 'ledger', { bg: 'graphite' });

/** Chips for a run of refs, separated by a plain space. */
export function chipPieces(refs: readonly number[]): Piece[] {
  return refs.flatMap((ref, index) => (index === 0 ? [chipPiece(ref)] : [piece(' '), chipPiece(ref)]));
}

export interface CitationChipProps {
  ref_: number | string;
}

export function CitationChip({ ref_ }: CitationChipProps) {
  return (
    <Text color={color('ledger')} backgroundColor={color('graphite')}>
      {`[${ref_}]`}
    </Text>
  );
}
