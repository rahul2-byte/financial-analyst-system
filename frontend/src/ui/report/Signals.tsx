import type { ReactNode } from 'react';
import type { ReportSignal } from '../../protocol/generated.js';
import { displayWidth } from '../../render/format.js';
import type { Piece } from '../../render/markdown.js';
import type { Token } from '../../render/theme.js';
import { INDENT, PieceLines, Section, alignLeft, alignRight, piece, spaces } from './layout.js';

export interface SignalsProps {
  signals: readonly ReportSignal[];
  width: number;
  /** Wide layouts add the strength bar and percentile. */
  wide: boolean;
}

const GLYPH: Record<ReportSignal['direction'], { glyph: string; tone: Token }> = {
  bullish: { glyph: '▲', tone: 'gain' },
  bearish: { glyph: '▼', tone: 'loss' },
  neutral: { glyph: '●', tone: 'dim' },
  unavailable: { glyph: '○', tone: 'dim' },
};

const BAR = 5;
const GAP = 2;

/** Python's 0..1 strength drawn as `▰▰▰▱▱`. No thresholds or labels are derived here. */
export function strengthBar(strength: number | null | undefined): string {
  if (strength == null) return ' '.repeat(BAR);
  const filled = Math.min(BAR, Math.max(0, Math.round(strength * BAR)));
  return '▰'.repeat(filled) + '▱'.repeat(BAR - filled);
}

/** Technical signals: direction glyph in the Python-supplied direction colour, strength bar when wide. */
export function Signals({ signals, width, wide }: SignalsProps): ReactNode {
  if (signals.length === 0) return null;
  const nameW = Math.min(18, Math.max(...signals.map((s) => displayWidth(s.name))));
  const valueW = Math.max(...signals.map((s) => displayWidth(s.value_text)));
  const stateW = Math.max(...signals.map((s) => 2 + displayWidth(s.state_text ?? (s.direction === 'unavailable' ? 'unavailable' : s.direction))));
  const rows = signals.map((s): Piece[] => {
    const g = GLYPH[s.direction];
    const state = s.state_text ?? (s.direction === 'unavailable' ? 'unavailable' : s.direction);
    const base: Piece[] = [
      spaces(INDENT),
      piece(alignLeft(s.name, nameW)),
      spaces(GAP),
      piece(alignRight(s.value_text, valueW)),
      spaces(GAP),
      piece(`${g.glyph} `, g.tone),
      piece(alignLeft(state, stateW - 2), s.direction === 'unavailable' ? 'dim' : undefined),
    ];
    if (wide) {
      base.push(spaces(GAP), piece(strengthBar(s.strength), s.direction === 'unavailable' ? 'faint' : g.tone));
      if (s.percentile_text) base.push(spaces(GAP), piece(s.percentile_text, 'dim'));
    }
    return base;
  });
  return (
    <Section title="Technical signals" width={width}>
      <PieceLines lines={rows} width={width} />
    </Section>
  );
}
