import { Box, Text } from 'ink';
import { memo } from 'react';
import { useElapsed } from './hooks/useElapsed.js';
import type { ActivityState } from '../state/types.js';
import { color } from '../render/theme.js';
import { SPINNER_FRAMES, formatElapsed, humanLabel, truncate } from '../render/format.js';

export interface LiveActivityProps {
  /** Spinner frame index; the caller advances it. No timers live here. */
  frame: number;
  /** `current_operation` from the presentation state. */
  operation: string | null;
  elapsedSeconds: number;
  /** `active_tools` keys from the presentation state (activity key is `tool:<key>`). */
  activeTools?: readonly string[];
  activities?: Readonly<Record<string, ActivityState>>;
  width: number;
}

const MAX_TOOLS = 3;

/**
 * Live region while a run is active: spinner, current operation, elapsed time and up to
 * three running tool labels. `model` and completed `provider` activities are never shown.
 */
export function LiveActivity({ frame, operation, elapsedSeconds, activeTools = [], activities = {}, width }: LiveActivityProps) {
  const spinnerCount = SPINNER_FRAMES.length;
  const spinner = SPINNER_FRAMES[((frame % spinnerCount) + spinnerCount) % spinnerCount] ?? SPINNER_FRAMES[0];
  const label = humanLabel(operation) ?? 'Working';
  // The spinner line already shows the current operation, so a tool with the same label is
  // left out of the tree: one active tool shows once.
  const tools = activeTools
    .map((key) => humanLabel(activities[`tool:${key}`]?.label))
    .filter((name): name is string => name !== null && name !== label)
    .slice(0, MAX_TOOLS);

  return (
    <Box flexDirection="column" width={width}>
      <Text>
        <Text color={color('ledger')}>{`${spinner} `}</Text>
        <Text color={color('paper')}>{`${truncate(label, Math.max(1, width - 12))}  `}</Text>
        <Text color={color('dim')}>{formatElapsed(elapsedSeconds)}</Text>
      </Text>
      {tools.map((name, index) => (
        <Text key={index} color={color('dim')}>
          {truncate(`  ⎿ ${name}`, width)}
        </Text>
      ))}
    </Box>
  );
}

export interface TickingActivityProps extends Omit<LiveActivityProps, 'frame' | 'elapsedSeconds'> {
  startedAt: number | null;
}

/**
 * `LiveActivity` with its own 100 ms clock. The ticking state lives here so only this
 * subtree re-renders while a run is active, not the whole app.
 */
export const TickingActivity = memo(function TickingActivity({ startedAt, ...rest }: TickingActivityProps) {
  const elapsed = useElapsed(true, startedAt);
  return <LiveActivity {...rest} frame={elapsed.frame} elapsedSeconds={elapsed.seconds} />;
});
