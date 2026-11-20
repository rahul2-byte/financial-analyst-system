import { Box } from 'ink';
import type { ReactNode } from 'react';
import type { ReportView } from '../../protocol/generated.js';
import { EvidenceBlock } from './EvidenceBlock.js';
import { Disclaimer, Prose } from './Prose.js';
import { ReportCard } from './ReportCard.js';
import { SourceList } from './SourceList.js';
import { contentWidth, isWide } from './layout.js';

export interface LookupCardProps {
  report: ReportView;
  width: number;
}

/** A quick lookup: the card, the answer, then only limitations, sources and the disclaimer. */
export function LookupCard({ report, width }: LookupCardProps): ReactNode {
  const w = contentWidth(width);
  const hasCard = !!(report.instrument || report.quote || report.sparkline);
  return (
    <Box flexDirection="column" width={w}>
      {hasCard ? (
        <ReportCard
          instrument={report.instrument}
          quote={report.quote}
          sparkline={report.sparkline}
          evidence={report.evidence}
          stanceText={report.stance_text}
          width={w}
          wide={isWide(width)}
        />
      ) : null}
      <Prose title="Answer" text={report.summary} width={w} />
      <EvidenceBlock evidence={report.evidence} limitations={report.limitations ?? []} width={w} />
      <SourceList sources={report.sources ?? []} width={w} />
      <Disclaimer text={report.disclaimer} width={w} />
    </Box>
  );
}
