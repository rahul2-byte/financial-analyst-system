import { Box } from 'ink';
import type { ReactNode } from 'react';
import type { ReportEvidence, ReportInstrument, ReportQuote, ReportSparkline } from '../../protocol/generated.js';
import type { Piece } from '../../render/markdown.js';
import type { Token } from '../../render/theme.js';
import { PieceRow, fitPieces, padPieces, piece, piecesWidth, splitRow } from './layout.js';
import { sparklineText } from './Sparkline.js';

export interface ReportCardProps {
  instrument: ReportInstrument | null | undefined;
  quote: ReportQuote | null | undefined;
  sparkline: ReportSparkline | null | undefined;
  evidence: ReportEvidence;
  stanceText?: string | null;
  width: number;
  /** Wide layouts keep the sparkline on the price row; narrow ones move it to its own row. */
  wide: boolean;
}

const DIRECTION_TONE: Record<string, Token> = { up: 'gain', down: 'loss', flat: 'dim' };

/** Evidence meter, e.g. `●●●○ 3/4 sources · limited`. Counts come straight from the source statuses. */
export function evidenceMeter(evidence: ReportEvidence): Piece[] {
  const sources = evidence.sources ?? [];
  const ok = sources.filter((s) => s.status === 'available').length;
  const out: Piece[] = [piece('Evidence ', 'dim')];
  if (sources.length > 0) {
    out.push(piece('●'.repeat(ok)), piece('○'.repeat(sources.length - ok), 'dim'), piece(` ${ok}/${sources.length} sources`, 'dim'));
  }
  out.push(piece(` ${sources.length > 0 ? '· ' : ''}`, 'dim'));
  out.push(evidence.status === 'limited' ? piece('limited', 'warn') : piece('complete', 'dim'));
  return out;
}

/** The header card: instrument, quote, sparkline, evidence meter and stance, drawn in a rounded box. */
export function ReportCard({ instrument, quote, sparkline, evidence, stanceText, width, wide }: ReportCardProps): ReactNode {
  const inner = width - 4; // `│ ` … ` │`
  const border = (text: string): Piece => piece(text, 'faint');
  const line = (content: readonly Piece[]): Piece[] => [
    border('│ '),
    ...padPieces(content, inner),
    border(' │'),
  ];

  const title = [instrument?.symbol, instrument?.name, instrument?.exchange].filter((p): p is string => !!p);
  const heading: Piece[] = title.length > 0 ? [piece(title.join(' · '), undefined, { bold: true })] : [];
  const headingWidth = piecesWidth(heading);
  const fittedHeading = fitPieces(heading, Math.max(1, width - 6));
  const topRow: Piece[] =
    headingWidth > 0
      ? [
          border('╭─ '),
          ...fittedHeading,
          border(` ${'─'.repeat(Math.max(0, width - 3 - piecesWidth(fittedHeading) - 2))}╮`),
        ]
      : [border(`╭${'─'.repeat(width - 2)}╮`)];

  const rows: Piece[][] = [];
  const tone = quote?.direction ? DIRECTION_TONE[quote.direction] : undefined;
  const spark: Piece[] = [];
  if (sparkline) {
    const range = `${sparkline.low_text} – ${sparkline.high_text}`;
    spark.push(
      piece(sparklineText(sparkline.points, 24), tone ?? 'dim'),
      piece(` ${sparkline.period_text}  ${range}`, 'dim'),
    );
  }
  if (quote) {
    const priceRow: Piece[] = [piece(quote.price_text, undefined, { bold: true })];
    if (quote.change_text) priceRow.push(piece('  '), piece(quote.change_text, tone ?? 'dim'));
    if (wide && spark.length > 0) priceRow.push(piece('    '), ...spark);
    const asOf = quote.as_of_text ? [piece(`as of ${quote.as_of_text}`, 'faint')] : [];
    rows.push(splitRow(priceRow, asOf, inner));
    if (!wide && spark.length > 0) rows.push(spark);
  } else if (spark.length > 0) {
    rows.push(spark);
  }
  const stance = stanceText ? [piece('Stance  ', 'dim'), piece(stanceText)] : [];
  rows.push(splitRow(evidenceMeter(evidence), stance, inner));

  return (
    <Box flexDirection="column" width={width}>
      <PieceRow pieces={topRow} width={width} />
      {rows.map((row, index) => (
        <PieceRow key={index} pieces={line(row)} width={width} />
      ))}
      <PieceRow pieces={[border(`╰${'─'.repeat(width - 2)}╯`)]} width={width} />
    </Box>
  );
}
