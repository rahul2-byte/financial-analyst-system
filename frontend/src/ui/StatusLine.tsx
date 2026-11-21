/**
 * One dim status line: session title and mode on the left; the
 * run hints while a run is active, otherwise a context hint, on the right.
 */
import { Box, Text } from 'ink';
import { memo } from 'react';

import { color, glyphs } from '../render/theme.js';

export const RUNNING_HINT = 'esc cancel · ctrl+o details · /help';

export interface StatusLineProps {
  readonly title: string;
  readonly mode: string;
  readonly running: boolean;
  /** Shown on the right while idle (for example context tokens). */
  readonly hint?: string;
}

export const StatusLine = memo(function StatusLine({ title, mode, running, hint = '' }: StatusLineProps) {
  const right = running ? RUNNING_HINT : hint;
  return (
    <Box justifyContent="space-between" width="100%">
      <Text color={color('dim')} wrap="truncate-end">
        {title} {glyphs.dot} {mode}
      </Text>
      <Text color={color('dim')} wrap="truncate-start">
        {right}
      </Text>
    </Box>
  );
});
