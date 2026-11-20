import { Box, Text } from 'ink';
import type { DisplaySource } from '../protocol/generated.js';
import { color } from '../render/theme.js';
import { truncate } from '../render/format.js';

export interface SourcesProps {
  sources: readonly DisplaySource[];
  width: number;
}

/** One numbered sources block per reply. The host is dim, and only shown when it differs from the label. */
export function Sources({ sources, width }: SourcesProps) {
  if (sources.length === 0) return null;
  return (
    <Box flexDirection="column" width={width}>
      <Text color={color('dim')}>Sources</Text>
      {sources.map((source, index) => {
        const host = source.host ?? null;
        const showHost = host !== null && host.trim() !== '' && host.toLowerCase() !== source.label.toLowerCase();
        // Gaps are trailing spaces of the segment before them, inside this one <Text>.
        const label = truncate(source.label, Math.max(1, width - 4));
        return (
          <Text key={`${source.url}-${index}`}>
            <Text color={color('dim')}>{`${index + 1}. `}</Text>
            <Text color={color('paper')}>{showHost ? `${label} ` : label}</Text>
            {showHost ? <Text color={color('dim')}>{`· ${host}`}</Text> : null}
          </Text>
        );
      })}
    </Box>
  );
}
