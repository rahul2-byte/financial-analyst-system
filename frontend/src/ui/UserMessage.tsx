import { Box, Text } from 'ink';
import { color } from '../render/theme.js';
import { padEnd, wrapWords } from '../render/format.js';

export interface UserMessageProps {
  text: string;
  width: number;
}

/** `› query` in paper bold on a graphite band, full width. */
export function UserMessage({ text, width }: UserMessageProps) {
  const inner = Math.max(1, width - 2);
  const lines = wrapWords(text, inner);
  return (
    <Box flexDirection="column" width={width}>
      {lines.map((line, index) => (
        <Text key={index} backgroundColor={color('graphite')}>
          <Text color={color('dim')} backgroundColor={color('graphite')}>
            {index === 0 ? '› ' : '  '}
          </Text>
          <Text color={color('paper')} backgroundColor={color('graphite')} bold>
            {padEnd(line, inner)}
          </Text>
        </Text>
      ))}
    </Box>
  );
}
