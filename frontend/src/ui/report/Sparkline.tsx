import { Text } from 'ink';
import { color, type Token } from '../../render/theme.js';

const BLOCKS = '▁▂▃▄▅▆▇█';

/** Map points already scaled to 0..1 by Python onto block glyphs. Nothing else is computed. */
export function sparklineText(points: readonly number[], maxPoints = Number.POSITIVE_INFINITY): string {
  const step = points.length > maxPoints ? points.length / maxPoints : 1;
  const out: string[] = [];
  for (let i = 0; i < points.length && out.length < maxPoints; i += step) {
    const value = points[Math.floor(i)] ?? 0;
    const level = Math.min(BLOCKS.length - 1, Math.max(0, Math.round(value * (BLOCKS.length - 1))));
    out.push(BLOCKS[level] ?? '▁');
  }
  return out.join('');
}

export interface SparklineProps {
  points: readonly number[];
  tone?: Token;
  maxPoints?: number;
}

export function Sparkline({ points, tone = 'dim', maxPoints }: SparklineProps) {
  return <Text color={color(tone)}>{sparklineText(points, maxPoints)}</Text>;
}
