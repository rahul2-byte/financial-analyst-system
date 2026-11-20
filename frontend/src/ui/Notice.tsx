import { Box, Text } from 'ink';
import { color, glyphs } from '../render/theme.js';

export type NoticeKind = 'warn' | 'fail' | 'info';

export interface NoticeProps {
  kind: NoticeKind;
  text: string;
  width: number;
}

const GLYPH: Record<NoticeKind, string> = {
  warn: glyphs.warn,
  fail: glyphs.fail,
  info: glyphs.dot,
};

const TONE: Record<NoticeKind, 'warn' | 'loss' | 'dim'> = {
  warn: 'warn',
  fail: 'loss',
  info: 'dim',
};

/** One-line notice with a prefix glyph: `⚠` warn, `✕` fail, `·` info. Only the glyph takes the tone colour. */
export function Notice({ kind, text, width }: NoticeProps) {
  return (
    <Box width={width}>
      <Text>
        <Text color={color(TONE[kind])}>{`${GLYPH[kind]} `}</Text>
        <Text color={color(kind === 'warn' ? 'paper' : 'dim')}>{text}</Text>
      </Text>
    </Box>
  );
}
