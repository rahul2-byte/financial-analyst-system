/**
 * Session picker. Replaces the composer while open: a filter
 * line and a list of saved sessions. ↑/↓ move, Enter selects, Esc closes.
 */
import { Box, Text } from 'ink';
import { useState } from 'react';

import type { SessionSummary } from '../protocol/generated.js';
import { color, glyphs } from '../render/theme.js';
import { useKeybindings, type Action } from './hooks/useKeybindings.js';

export const PICKER_ROWS = 8;

/** Case-insensitive match on title or id prefix. An empty query keeps everything. */
export function filterSessions(sessions: readonly SessionSummary[], query: string): SessionSummary[] {
  const needle = query.trim().toLowerCase();
  if (needle === '') return [...sessions];
  return sessions.filter(
    (session) => session.title.toLowerCase().includes(needle) || session.id.toLowerCase().startsWith(needle),
  );
}

export interface SessionPickerProps {
  readonly sessions: readonly SessionSummary[];
  readonly onSelect: (id: string) => void;
  readonly onClose: () => void;
  readonly isActive?: boolean;
}

export function SessionPicker({ sessions, onSelect, onClose, isActive = true }: SessionPickerProps) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const matches = filterSessions(sessions, query);
  const index = matches.length === 0 ? 0 : Math.min(selected, matches.length - 1);

  const onAction = (action: Action): void => {
    switch (action.type) {
      case 'pickerUp':
        setSelected(Math.max(0, index - 1));
        return;
      case 'pickerDown':
        setSelected(Math.min(Math.max(0, matches.length - 1), index + 1));
        return;
      case 'pickerSelect': {
        const chosen = matches[index];
        if (chosen !== undefined) onSelect(chosen.id);
        return;
      }
      case 'pickerClose':
        onClose();
        return;
      case 'pickerInsert':
        setQuery((current) => current + action.text);
        setSelected(0);
        return;
      case 'pickerBackspace':
        setQuery((current) => Array.from(current).slice(0, -1).join(''));
        setSelected(0);
        return;
      default:
        return;
    }
  };

  useKeybindings({
    mode: 'picker',
    getContext: () => ({ composerEmpty: true, completionOpen: false, charBeforeCursor: '' }),
    onAction,
    isActive,
  });

  const start = Math.min(Math.max(0, index - PICKER_ROWS + 1), Math.max(0, matches.length - PICKER_ROWS));
  const visible = matches.slice(start, start + PICKER_ROWS);

  return (
    <Box flexDirection="column">
      <Text color={color('dim')}>Resume a session · ↑/↓ move · enter resume · esc close</Text>
      <Text>
        <Text color={color('ledger')}>{glyphs.prompt} </Text>
        {query}
        <Text inverse> </Text>
      </Text>
      {matches.length === 0 ? (
        <Text color={color('dim')}>No sessions match &quot;{query}&quot;</Text>
      ) : (
        visible.map((session, offset) => {
          const row = start + offset;
          const isSelected = row === index;
          return (
            <Box key={session.id}>
              <Text>
                <Text color={isSelected ? color('ledger') : undefined}>
                  {`${isSelected ? `${glyphs.prompt} ` : '  '}${session.title}  `}
                </Text>
                <Text color={color('dim')}>
                  {`${session.id.slice(0, 8)} ${glyphs.dot} ${session.message_count} msgs ${glyphs.dot} ${session.last_activity}`}
                </Text>
              </Text>
            </Box>
          );
        })
      )}
    </Box>
  );
}
