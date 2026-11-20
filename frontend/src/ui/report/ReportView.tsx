import { Box } from 'ink';
import type { ReactNode } from 'react';
import type { ReportView as ReportViewData } from '../../protocol/generated.js';
import { Drivers } from './Drivers.js';
import { EvidenceBlock } from './EvidenceBlock.js';
import { FinalView } from './FinalView.js';
import { KeyFigures } from './KeyFigures.js';
import { LookupCard } from './LookupCard.js';
import { Disclaimer, Prose } from './Prose.js';
import { contentWidth, isWide } from './layout.js';
import { ReportCard } from './ReportCard.js';
import { Risks } from './Risks.js';
import { Signals } from './Signals.js';
import { SourceList } from './SourceList.js';

export interface ReportViewProps {
  report: ReportViewData;
  width: number;
}

/**
 * The structured answer, in reading order: the card, then the call, then the evidence.
 * A block with no data is left out. Layout only: every value arrives formatted from Python.
 */
export function ReportView({ report, width }: ReportViewProps): ReactNode {
  if (report.kind === 'lookup') return <LookupCard report={report} width={width} />;
  const w = contentWidth(width);
  const wide = isWide(width);
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
          wide={wide}
        />
      ) : null}
      <Prose title="Summary" text={report.summary} width={w} />
      <KeyFigures figures={report.key_figures ?? []} width={w} wide={wide} />
      <Signals signals={report.signals ?? []} width={w} wide={wide} />
      <Drivers drivers={report.drivers ?? []} width={w} />
      <Risks risks={report.risks ?? []} width={w} />
      {report.final_view ? <FinalView text={report.final_view} width={w} /> : null}
      {report.detailed_analysis ? <Prose title="Detailed analysis" text={report.detailed_analysis} width={w} /> : null}
      <EvidenceBlock evidence={report.evidence} limitations={report.limitations ?? []} width={w} />
      <SourceList sources={report.sources ?? []} width={w} />
      <Disclaimer text={report.disclaimer} width={w} />
    </Box>
  );
}
