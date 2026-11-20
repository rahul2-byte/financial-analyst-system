import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { render } from 'ink-testing-library';
import type { ReactElement } from 'react';
import type { ReportView as ReportData } from '../../src/protocol/generated.js';
import { parseReport } from '../../src/ui/report/parse.js';

export const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;
export const RAW_ID = /\b[a-z_]+:[a-z0-9_]+\b/;
export const DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'goldens', 'reports');

export function loadReport(kind: 'full' | 'partial' | 'lookup'): ReportData {
  const data = JSON.parse(readFileSync(path.join(DIR, `report-${kind}.json`), 'utf8')) as {
    finished: { report: unknown };
  };
  const report = parseReport(data.finished.report);
  if (report === null) throw new Error(`fixture ${kind} did not parse`);
  return report;
}

export function frameOf(element: ReactElement): string {
  const { lastFrame, unmount } = render(element);
  const frame = (lastFrame() ?? '').replace(ANSI, '');
  unmount();
  return frame;
}
