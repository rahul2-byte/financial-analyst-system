import { Box } from 'ink';
import type { ReactNode } from 'react';
import { inlineSegments, render } from '../../render/markdown.js';
import { INDENT, PieceLines, Section, piece, spaces, wrapRows } from './layout.js';

/** Markdown prose indented under a section title. */
export function Prose({ title, text, width }: { title: string; text: string; width: number }): ReactNode {
  if (text.trim() === '') return null;
  return (
    <Section title={title} width={width}>
      <Box marginLeft={INDENT} width={width - INDENT}>
        {render(text, width - INDENT)}
      </Box>
    </Section>
  );
}

/** The research disclaimer, dim, under the sources. */
export function Disclaimer({ text, width }: { text: string; width: number }): ReactNode {
  const lines = wrapRows(
    inlineSegments(text).map((s) => ({ ...s, style: { ...s.style, color: piece('', 'dim').style.color } })),
    width,
    [spaces(INDENT)],
    [spaces(INDENT)],
  );
  return (
    <Box marginTop={1} width={width}>
      <PieceLines lines={lines} width={width} />
    </Box>
  );
}

