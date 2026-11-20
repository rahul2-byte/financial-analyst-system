import { Box, Text } from 'ink';
import { color } from '../render/theme.js';

export interface CommandOutputProps {
  lines: readonly string[];
  width: number;
}

/** Lines printed by a local slash command (e.g. `/help`), committed into scrollback. */
export function CommandOutput({ lines, width }: CommandOutputProps) {
  if (lines.length === 0) return null;
  return (
    <Box flexDirection="column" width={width}>
      {lines.map((line, index) => (
        <Text key={index} color={color('paper')}>
          {line === '' ? ' ' : line}
        </Text>
      ))}
    </Box>
  );
}
