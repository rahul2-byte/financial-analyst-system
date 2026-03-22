// frontend/types/index.ts

export type Role = 'user' | 'assistant';

export type ChartType = 'line' | 'bar' | 'area';

/**
 * Generic data point for charts.
 */
export interface ChartDataPoint {
  [key: string]: string | number | undefined;
}

/**
 * Common financial data shapes for better strictness in chart components.
 */
export interface TimeSeriesDataPoint extends ChartDataPoint {
  timestamp: string | number;
}

/**
 * Specific shape for OHLC (Open, High, Low, Close) financial data.
 */
export interface OHLCDataPoint extends TimeSeriesDataPoint {
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

/**
 * Represents a chart payload for visualization.
 * Uses generics to allow better type inference of data keys.
 */
export interface ChartPayload<T extends ChartDataPoint = ChartDataPoint> {
  title: string;
  chartType: ChartType; // Renamed from type to avoid collision in flat event structure
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

// SSE Event Types
export type StreamEvent = 
  | { type: 'text_delta'; content: string }
  | ({ type: 'chart' } & ChartPayload)
  | { type: 'status'; message: string }
  | { type: 'error'; message?: string; content?: string }
  | ({ type: 'tool_status' } & ToolStatus)
  | { type: 'done' };

/**
 * Represents a single message in the chat history.
 */
export interface Message {
  id: string;
  role: Role;
  content: string; // Markdown text
  charts?: ChartPayload[]; // Attached charts
  reasoning_steps?: ToolStatus[]; // Agent reasoning steps
  timestamp: Date;
  isStreaming?: boolean;
}
