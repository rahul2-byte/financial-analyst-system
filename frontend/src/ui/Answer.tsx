import { Box, Text } from 'ink';
import { color } from '../render/theme.js';
import { render } from '../render/markdown.js';

export interface AnswerProps {
  /** Sanitized Markdown. */
  text: string;
  width: number;
  /** The answer bullet `●` is shown on the first chunk only; later chunks indent. */
  showBullet?: boolean;
}

const GUTTER = 2;

/** A committed answer block. The bullet sits on the first line of the text. */
export function Answer({ text, width, showBullet = true }: AnswerProps) {
  if (text.trim() === '') return null;
  const inner = Math.max(1, width - GUTTER);
  return (
    <Box flexDirection="row" width={width}>
      <Box width={GUTTER} flexShrink={0}>
        <Text color={color('ledger')}>{showBullet ? '●' : ' '}</Text>
      </Box>
      <Box flexDirection="column" width={inner}>
        {render(text, inner)}
      </Box>
    </Box>
  );
}
