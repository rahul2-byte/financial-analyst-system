/**
 * Slash-command completion rows under the composer: at most 8 rows, with the
 * selected row in ledger colour.
 */
import { Box, Text } from 'ink';

import type { CommandSpec } from '../commands/registry.js';
import { color, glyphs } from '../render/theme.js';

export const COMPLETION_ROWS = 8;

/** The window of rows to show, chosen so the selected row stays visible. */
export function completionWindow(
  count: number,
  selected: number,
  rows: number = COMPLETION_ROWS,
): { start: number; end: number } {
  if (count <= rows) return { start: 0, end: count };
  const start = Math.min(Math.max(0, selected - rows + 1), count - rows);
  return { start, end: start + rows };
}

export interface CompletionProps {
  readonly items: readonly CommandSpec[];
  readonly selected: number;
}

export function Completion({ items, selected }: CompletionProps) {
  if (items.length === 0) return null;
  const { start, end } = completionWindow(items.length, selected);
  return (
    <Box flexDirection="column">
      {items.slice(start, end).map((item, offset) => {
        const index = start + offset;
        const isSelected = index === selected;
        const usage = item.args ? `/${item.name} ${item.args}` : `/${item.name}`;
        return (
          <Box key={item.name}>
            <Text>
              <Text color={isSelected ? color('ledger') : undefined}>
                {`${isSelected ? `${glyphs.prompt} ` : '  '}${usage.padEnd(30)}`}
              </Text>
              <Text color={color('dim')}>{item.help}</Text>
            </Text>
          </Box>
        );
      })}
    </Box>
  );
}
