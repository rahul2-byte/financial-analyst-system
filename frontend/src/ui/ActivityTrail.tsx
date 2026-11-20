import { Box, Text } from 'ink';
import type { ActivityState } from '../state/types.js';
import { color } from '../render/theme.js';
import { humanLabel, pluralize, truncate } from '../render/format.js';
import { trailRows, type TrailRow } from '../state/transcript.js';

export interface ActivityTrailProps {
  /** Tool count. When omitted, counted from the `tool:` keys of `activities`. */
  toolCount?: number;
  /** Nouns of failed tools, from `display.failed_nouns`. */
  failedNouns?: readonly string[];
  /** Presentation activities; only `tool:` keys are shown, `model` and `provider` never. */
  activities?: Readonly<Record<string, ActivityState>>;
  /** Tool lines to show when `expanded`. Takes precedence over `activities`. */
  rows?: readonly TrailRow[];
  /** Ctrl+O: list each tool under the summary line. */
  expanded?: boolean;
  width: number;
}

const TOOL_PREFIX = 'tool:';

/**
 * Collapsed evidence summary, mirroring `render_activity`. Renders nothing for a
 * chat-only run (no tool activities). Raw tool ids are never printed: a tool without a
 * human label is left out.
 */
export function ActivityTrail({ toolCount, failedNouns = [], activities = {}, rows: given, expanded = false, width }: ActivityTrailProps) {
  const toolEntries = Object.entries(activities).filter(([key]) => key.startsWith(TOOL_PREFIX));
  const count = toolCount ?? toolEntries.length;
  if (count <= 0) return null;

  const failed = failedNouns.map((noun) => humanLabel(noun)).filter((noun): noun is string => noun !== null);
  const summary = `⏺ Gathered evidence · ${pluralize(count, 'tool')}` +
    failed.map((noun) => ` · ${noun} unavailable`).join('');

  const rows = expanded ? (given ?? trailRows(activities)) : [];

  return (
    <Box flexDirection="column" width={width} marginTop={1}>
      <Text color={color('dim')}>{truncate(summary, width)}</Text>
      {rows.map((row, index) => {
        const tail = row.status === 'running' ? 'running' : row.status === 'completed' ? 'done' : '';
        return (
          <Text key={index} color={color('dim')}>
            {'  ⎿ '}
            {row.status === 'failed' ? <Text color={color('loss')}>✕ </Text> : null}
            {truncate(`${row.label}${tail === '' ? ' · failed' : ` · ${tail}`}${row.detail ? ` · ${row.detail}` : ''}`, width - 4)}
          </Text>
        );
      })}
    </Box>
  );
}
