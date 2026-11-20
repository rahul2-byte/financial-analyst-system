import { Box, Text } from 'ink';
import type { DisplayCandidate } from '../protocol/generated.js';
import { color } from '../render/theme.js';
import { displayWidth, padEnd } from '../render/format.js';

export interface ClarificationProps {
  candidates: readonly DisplayCandidate[];
  /** Passthrough lines from `display.lines`, already sanitized. */
  lines: readonly string[];
  width: number;
}

/** Aligned `SYMBOL  Name · EX` rows, then any passthrough lines. */
export function Clarification({ candidates, lines, width }: ClarificationProps) {
  if (candidates.length === 0 && lines.length === 0) return null;
  const symbolWidth = Math.max(0, ...candidates.map((candidate) => displayWidth(candidate.symbol)));
  return (
    <Box flexDirection="column" width={width}>
      {candidates.map((candidate, index) => (
        <Text key={`${candidate.symbol}-${index}`}>
          <Text color={color('paper')} bold>
            {`${padEnd(candidate.symbol, symbolWidth)}  `}
          </Text>
          <Text color={color('paper')}>{candidate.exchange ? `${candidate.name} ` : candidate.name}</Text>
          {candidate.exchange ? <Text color={color('dim')}>{`· ${candidate.exchange}`}</Text> : null}
        </Text>
      ))}
      {lines.map((line, index) => (
        <Text key={`line-${index}`} color={color('paper')}>
          {line === '' ? ' ' : line}
        </Text>
      ))}
    </Box>
  );
}
