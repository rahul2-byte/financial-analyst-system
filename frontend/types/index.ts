// frontend/types/index.ts

export type Role = 'user' | 'assistant';

export type ChartType = 'line' | 'bar' | 'area';

export interface ChartDataPoint {
  [key: string]: string | number | undefined;
}

export interface TimeSeriesDataPoint extends ChartDataPoint {
  timestamp: string | number;
}

export interface OHLCDataPoint extends TimeSeriesDataPoint {
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface ChartPayload<T extends ChartDataPoint = ChartDataPoint> {
  title: string;
  chartType: ChartType;
  data: T[];
  xAxisKey: Extract<keyof T, string>;
  seriesKeys: Extract<keyof T, string>[];
}

export interface ToolStatus {
  tool_id: string;
  step_number: number;
  agent: string;
  tool_name: string;
  status: 'running' | 'completed' | 'error';
  input: string;
  output?: string;
}

export type StreamEvent =
  | { type: 'text_delta'; content: string }
  | ({ type: 'chart' } & ChartPayload)
  | { type: 'status'; message: string }
  | { type: 'error'; message?: string; content?: string }
  | ({ type: 'tool_status' } & ToolStatus)
  | { type: 'final_payload'; payload: unknown }
  | { type: 'done' };

export interface Message {
  id: string;
  role: Role;
  content: string;
  charts?: ChartPayload[];
  reasoning_steps?: ToolStatus[];
  structured_output?: unknown;
  timestamp: Date;
  isStreaming?: boolean;
}
