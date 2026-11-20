import { Box, Text } from 'ink';
import { color } from '../render/theme.js';
import { truncate } from '../render/format.js';

export interface HeaderProps {
  title: string;
  mode: string;
  model: string;
  width: number;
}

/** `FIN-AI` in ledger, then session title · mode · model in dim. Printed once into scrollback. */
export function Header({ title, mode, model, width }: HeaderProps) {
  const meta = [title, mode, model]
    .map((part) => part.trim())
    .filter((part) => part !== '')
    .join(' · ');
  // Same pattern as the other rows: one parent <Text>, with the two-space gap trailing the brand.
  return (
    <Box width={width}>
      <Text>
        <Text color={color('ledger')} bold>
          {meta !== '' ? 'FIN-AI  ' : 'FIN-AI'}
        </Text>
        {meta !== '' ? <Text color={color('dim')}>{truncate(meta, Math.max(0, width - 8))}</Text> : null}
      </Text>
    </Box>
  );
}
