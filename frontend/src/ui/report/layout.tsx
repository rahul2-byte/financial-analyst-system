/**
 * Row primitives for the report components. A row is one line of styled pieces that is
 * fitted to its width before it reaches Ink, so a table row can never wrap and a card
 * line always lands on the same border column. Colours come from `theme.ts` only.
 */
import { Box, Text } from 'ink';
import type { ReactNode } from 'react';
import { color, type Token } from '../../render/theme.js';
import { displayWidth, truncate } from '../../render/format.js';
import { renderPiece, wrapSegments, type Piece, type Segment } from '../../render/markdown.js';

/** Section content is indented two columns from the transcript edge. */
export const INDENT = 2;

export interface PieceOptions {
  bold?: boolean;
  bg?: Token;
}

/** A piece in a theme colour. No tone means the row's base colour (paper). */
export function piece(text: string, tone?: Token, options: PieceOptions = {}): Piece {
  return {
    text,
    style: {
      color: tone === undefined ? undefined : color(tone),
      backgroundColor: options.bg === undefined ? undefined : color(options.bg),
      bold: options.bold,
    },
  };
}

export const spaces = (count: number): Piece => piece(' '.repeat(Math.max(0, count)));

export function piecesWidth(pieces: readonly Piece[]): number {
  return pieces.reduce((sum, p) => sum + displayWidth(p.text), 0);
}

/** Cut a row to `width` cells, ending with `…` where it was cut. */
export function fitPieces(pieces: readonly Piece[], width: number): Piece[] {
  const out: Piece[] = [];
  let used = 0;
  for (const p of pieces) {
    const w = displayWidth(p.text);
    if (used + w <= width) {
      out.push(p);
      used += w;
      continue;
    }
    const room = width - used;
    if (room > 0) out.push({ text: truncate(p.text, room), style: p.style });
    break;
  }
  return out;
}

/** Pad a row with trailing spaces to exactly `width` cells (cutting it first if longer). */
export function padPieces(pieces: readonly Piece[], width: number): Piece[] {
  const fitted = fitPieces(pieces, width);
  return [...fitted, spaces(width - piecesWidth(fitted))];
}

/** `left` at the start, `right` flush with the end. `right` is dropped if it cannot fit with a gap. */
export function splitRow(left: readonly Piece[], right: readonly Piece[], width: number): Piece[] {
  const rightWidth = piecesWidth(right);
  if (rightWidth === 0 || rightWidth + 1 >= width) return fitPieces(left, width);
  const room = width - rightWidth - 1;
  const fitted = fitPieces(left, room);
  return [...fitted, spaces(width - piecesWidth(fitted) - rightWidth), ...right];
}

/** Right-align `text` in `width` cells. */
export const alignRight = (text: string, width: number): string =>
  ' '.repeat(Math.max(0, width - displayWidth(text))) + text;

/** Left-align `text` in `width` cells, truncating with `…`. */
export function alignLeft(text: string, width: number): string {
  const cut = truncate(text, width);
  return cut + ' '.repeat(Math.max(0, width - displayWidth(cut)));
}

export interface PieceRowProps {
  pieces: readonly Piece[];
  width: number;
}

/** One line. Never wraps: the pieces are fitted to `width` first. */
export function PieceRow({ pieces, width }: PieceRowProps): ReactNode {
  return (
    <Box width={width}>
      <Text wrap="truncate-end" color={color('paper')}>
        {fitPieces(pieces, width).map((p, index) => renderPiece(p, index))}
      </Text>
    </Box>
  );
}

export interface SectionProps {
  title: string;
  width: number;
  children: ReactNode;
  /** Right-hand note on the title row, e.g. column headers. Fixed-width cells line up with the rows. */
  note?: readonly Piece[];
}

/** Report body width: wide terminals do not stretch tables across the whole screen. */
export const CONTENT_MAX = 110;
/** From this width the card keeps the sparkline inline and tables show every column. */
export const WIDE = 100;
export const contentWidth = (width: number): number => Math.max(20, Math.min(width, CONTENT_MAX));
export const isWide = (width: number): boolean => width >= WIDE;

/** A titled block: a blank line, the ledger-bold title, then the rows. */
export function Section({ title, width, children, note }: SectionProps): ReactNode {
  const heading = [spaces(INDENT), piece(title, 'ledger', { bold: true })];
  return (
    <Box flexDirection="column" width={width} marginTop={1}>
      <PieceRow pieces={note ? splitRow(heading, note, width) : heading} width={width} />
      {children}
    </Box>
  );
}

/** Give segments without a colour of their own a base tone (e.g. dim for minor drivers). */
export function tint(segments: readonly Segment[], tone?: Token): Segment[] {
  if (tone === undefined) return [...segments];
  return segments.map((s) => (s.style.color === undefined ? { ...s, style: { ...s.style, color: color(tone) } } : s));
}

/** Wrap `segments` into rows of `width`, each starting with `first` (line 1) or `hang` (the rest). */
export function wrapRows(
  segments: readonly Segment[],
  width: number,
  first: readonly Piece[],
  hang: readonly Piece[],
): Piece[][] {
  const lead = Math.max(piecesWidth(first), piecesWidth(hang));
  const lines = wrapSegments(segments, Math.max(1, width - lead));
  return lines.map((line, index) => {
    const prefix = index === 0 ? first : hang;
    return [...prefix, spaces(lead - piecesWidth(prefix)), ...line];
  });
}

export interface PieceLinesProps {
  lines: readonly (readonly Piece[])[];
  width: number;
}

/** A column of single-line rows. */
export function PieceLines({ lines, width }: PieceLinesProps): ReactNode {
  return (
    <Box flexDirection="column" width={width}>
      {lines.map((line, index) => (
        <PieceRow key={index} pieces={line} width={width} />
      ))}
    </Box>
  );
}
