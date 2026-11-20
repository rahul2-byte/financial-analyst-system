/**
 * Inline command and key reference. The text comes from the
 * command registry, so `/help` and this panel cannot drift apart.
 */
import { Box, Text } from 'ink';

import { helpLines } from '../commands/registry.js';
import { color } from '../render/theme.js';

export function HelpPanel() {
  return (
    <Box flexDirection="column">
      {helpLines().map((line, index) => (
        <Text key={index} color={line === 'Commands' || line === 'Keys' ? color('ledger') : undefined}>
          {line === '' ? ' ' : line}
        </Text>
      ))}
    </Box>
  );
}
