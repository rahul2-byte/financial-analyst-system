import { Box } from 'ink';
import type { TranscriptItem } from '../state/transcript.js';
import { Header } from './Header.js';
import { UserMessage } from './UserMessage.js';
import { ActivityTrail } from './ActivityTrail.js';
import { Answer } from './Answer.js';
import { Sources } from './Sources.js';
import { Clarification } from './Clarification.js';
import { Notice, type NoticeKind } from './Notice.js';
import { RunFooter } from './RunFooter.js';
import { CommandOutput } from './CommandOutput.js';
import { ReportView } from './report/ReportView.js';

export interface TranscriptItemViewProps {
  item: TranscriptItem;
  width: number;
}

/** Notice tones in `transcript.ts` mapped to the glyph kinds in `Notice`. */
const NOTICE_KIND: Record<'warn' | 'loss' | 'dim', NoticeKind> = {
  warn: 'warn',
  loss: 'fail',
  dim: 'info',
};

/**
 * Renders any committed transcript item. Pure: the item and width are the only inputs.
 * `Static` maps over this in P6. Blank-line spacing between items is added here so
 * the child components stay position-free.
 */
export function TranscriptItemView({ item, width }: TranscriptItemViewProps) {
  switch (item.kind) {
    case 'header':
      return <Header title={item.title} mode={item.mode} model={item.model} width={width} />;
    case 'user':
      return (
        <Box marginTop={1}>
          <UserMessage text={item.text} width={width} />
        </Box>
      );
    case 'activity-trail':
      // Chat-only runs have no trail, so no margin either.
      if (item.toolCount <= 0) return null;
      return (
        <ActivityTrail
          toolCount={item.toolCount}
          failedNouns={item.failedNouns}
          rows={item.rows}
          expanded={!item.collapsed}
          width={width}
        />
      );
    case 'answer-chunk':
      return (
        <Box marginTop={1}>
          <Answer text={item.text} width={width} showBullet={item.index === 0} />
        </Box>
      );
    case 'sources':
      return (
        <Box marginTop={1}>
          <Sources sources={item.sources} width={width} />
        </Box>
      );
    case 'report':
      return (
        <Box marginTop={1}>
          <ReportView report={item.report} width={width} />
        </Box>
      );
    case 'clarification':
      return (
        <Box marginTop={1}>
          <Clarification candidates={item.candidates} lines={item.lines} width={width} />
        </Box>
      );
    case 'notice':
      return (
        <Box marginTop={1}>
          <Notice kind={NOTICE_KIND[item.tone]} text={item.text} width={width} />
        </Box>
      );
    case 'run-footer':
      return (
        <Box marginTop={1}>
          <RunFooter
            status={item.status}
            elapsedMs={item.elapsedMs}
            toolCount={item.toolCount}
            sourceCount={item.sourceCount}
            partial={item.partial}
            unavailable={item.unavailable}
            reason={item.reason}
            width={width}
          />
        </Box>
      );
    case 'command-output':
      return (
        <Box marginTop={1}>
          <CommandOutput lines={item.lines} width={width} />
        </Box>
      );
  }
}
