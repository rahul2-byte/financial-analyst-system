import { Box, Text } from 'ink';
import { color, glyphs } from '../render/theme.js';
import { displayWidth, formatSeconds, pluralize, truncate } from '../render/format.js';

export interface RunFooterProps {
  /** Terminal status of the run, e.g. `completed`, `failed`, `cancelled`. */
  status: string;
  elapsedMs: number | null;
  toolCount: number;
  sourceCount?: number;
  partial: boolean;
  /** Names of evidence that could not be fetched, shown after `partial`. */
  unavailable?: readonly string[];
  /** Short failure reason, shown after `failed`. */
  reason?: string | null;
  width: number;
}

const FAILED = new Set(['failed', 'error']);
const CANCELLED = new Set(['cancelled', 'canceled']);

/**
 * One status line under a run, e.g. `◐ partial · news unavailable · 12.4s · 4 tools · 3 sources`.
 * `✓` complete, `◐` partial (completed, but some evidence was unavailable), `✕ failed · reason`,
 * `· cancelled`. A failed or cancelled run is never "partial": its state is the failure.
 */
export function RunFooter({
  status,
  elapsedMs,
  toolCount,
  sourceCount = 0,
  partial,
  unavailable = [],
  reason = null,
  width,
}: RunFooterProps) {
  const failed = FAILED.has(status);
  const cancelled = CANCELLED.has(status);
  const half = partial && !failed && !cancelled;
  const glyph = failed ? glyphs.fail : cancelled ? glyphs.dot : half ? '◐' : glyphs.ok;
  const glyphColor = failed ? color('loss') : cancelled ? color('dim') : half ? color('warn') : color('gain');

  const lead = failed ? 'failed' : cancelled ? 'cancelled' : half ? 'partial' : null;
  const rest: string[] = [];
  if (half && unavailable.length > 0) rest.push(`${unavailable.join(', ')} unavailable`);
  if (failed && reason) rest.push(reason);
  if (elapsedMs !== null) rest.push(formatSeconds(elapsedMs));
  if (toolCount > 0) rest.push(pluralize(toolCount, 'tool'));
  if (sourceCount > 0) rest.push(pluralize(sourceCount, 'source'));

  const sep = ` ${glyphs.dot} `;
  const room = Math.max(1, width - displayWidth(`${glyph} `) - (lead ? displayWidth(lead) : 0));
  const tail = truncate((lead && rest.length > 0 ? sep : '') + rest.join(sep), room);

  return (
    <Box width={width}>
      <Text wrap="truncate-end">
        <Text color={glyphColor}>{`${glyph} `}</Text>
        {lead ? <Text color={color(half ? 'warn' : failed ? 'loss' : 'dim')}>{lead}</Text> : null}
        <Text color={color('dim')}>{tail}</Text>
      </Text>
    </Box>
  );
}
